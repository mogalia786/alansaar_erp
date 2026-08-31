from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Booking
from events.models import Stall, Event
from events.views import _load_svg_content
from .pricing import booking_totals
import json


@login_required
def thank_you(request, pk):
    booking = get_object_or_404(Booking, pk=pk, exhibitor=request.user)
    return render(request, 'bookings/thank_you.html', {'booking': booking, 'show_ack': False})

@login_required
def thank_you_update(request, pk):
    booking = get_object_or_404(Booking, pk=pk, exhibitor=request.user)
    return render(request, 'bookings/thank_you.html', {'booking': booking, 'show_ack': True})

@login_required
def my_bookings(request):
    bookings = request.user.bookings.all().select_related('event', 'stall')
    my_booked_stall_ids = set(bookings.values_list('stall_id', flat=True))

    events = Event.objects.filter(stalls__isnull=False).distinct()
    if not events.exists():
        events = Event.objects.all()

    svg_content, svg_w, svg_h = _load_svg_content()
    event_groups = []
    for event in events:
        all_stalls = event.stalls.all().select_related('zone').order_by('name')

        all_stalls_data = [{
            'id': s.id, 'name': s.name,
            'x': s.position_x, 'y': s.position_y,
            'w': s.width, 'h': s.height,
            'status': s.status,
            'is_mine': s.id in my_booked_stall_ids,
            'price': float(s.total_price),
            'size_sqm': float(s.size_sqm),
            'zone': s.zone.name if s.zone else '',
        } for s in all_stalls]

        ev_bookings = [b for b in bookings if b.event_id == event.id]

        event_groups.append({
            'event': event,
            'bookings': ev_bookings,
            'svg_content': svg_content,
            'svg_w': svg_w,
            'svg_h': svg_h,
            'stalls_data': json.dumps(all_stalls_data),
            'ev_id': event.id,
        })

    return render(request, 'bookings/list.html', {
        'bookings': bookings,
        'event_groups': event_groups,
    })


@login_required
def booking_detail(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    if booking.exhibitor != request.user and not request.user.is_staff:
        from django.http import Http404
        raise Http404
    from events.models import AccessoryType
    accessories = AccessoryType.objects.filter(is_active=True)
    paid_amount = booking.amount_paid
    balance_due = booking.balance_due
    line = getattr(booking, 'invoice_line', None)
    if line is not None:
        paid_amount = line.invoice.amount_paid
        balance_due = line.invoice.balance_due
    return render(request, 'bookings/detail.html', {
        'booking': booking,
        'accessories': accessories,
        'paid_amount': paid_amount,
        'balance_due': balance_due,
        'invoice': line.invoice if line is not None else None,
    })


@login_required
def book_stall(request, event_id, stall_id):
    event = get_object_or_404(Event, pk=event_id)
    stall = get_object_or_404(Stall, pk=stall_id, event=event)
    if not request.user.is_verified:
        messages.error(request, 'Your registration is still pending approval. You will be able to make a booking once the admin team authorises your account.')
        return redirect('floor_plan_view', event_id=event_id)
    if stall.status != 'available':
        messages.error(request, 'This stall is no longer available.')
        return redirect('floor_plan_view', event_id=event_id)
    if request.method == 'POST':
        import uuid
        from decimal import Decimal
        ref = f"BK-{uuid.uuid4().hex[:8].upper()}"
        requires_power = request.POST.get('requires_power') == 'on'
        elec_dep = event.electricity_deposit if requires_power else Decimal('0')
        subtotal, vat = booking_totals(stall.total_price, elec_dep, Decimal('0'), float(event.vat_rate) / 100)
        total = subtotal
        booking = Booking.objects.create(
            booking_reference=ref,
            event=event,
            exhibitor=request.user,
            stall=stall,
            stall_price=stall.total_price,
            subtotal=subtotal,
            vat_amount=vat,
            total_amount=total,
            balance_due=total,
            electricity_deposit=elec_dep,
            fascia_name=request.POST.get('fascia_name', '')[:28],
            requires_power=requires_power,
            power_amps=int(request.POST.get('power_amps', 0)),
            requires_water=request.POST.get('requires_water') == 'on',
            require_stand_build=request.POST.get('require_stand_build') == 'on',
            require_remove_side_walls=request.POST.get('require_remove_side_walls') == 'on',
            require_floor_mat=request.POST.get('require_floor_mat') == 'on',
            require_carpet=request.POST.get('require_carpet') == 'on',
            require_extra_plugs=request.POST.get('require_extra_plugs') == 'on',
            require_extra_lights=request.POST.get('require_extra_lights') == 'on',
            special_requirements=request.POST.get('special_requirements', ''),
            side_wall_removal=request.POST.get('side_wall_removal', 'none'),
        )
        stall.status = 'reserved'
        stall.save()
        from notifications.utils import send_booking_received
        try:
            send_booking_received(booking)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f'Failed to send booking received email: {e}')
        messages.success(request, f'Booking {ref} created!')
        return redirect('thank_you', pk=booking.pk)
    return redirect('floor_plan_view', event_id=event_id)


@login_required
def update_booking(request, pk):
    booking = get_object_or_404(Booking, pk=pk, exhibitor=request.user)
    if request.method == 'POST':
        from decimal import Decimal
        booking.fascia_name = request.POST.get('fascia_name', '')[:28]
        booking.requires_power = request.POST.get('requires_power') == 'on'
        booking.power_amps = int(request.POST.get('power_amps', 0))
        booking.requires_water = request.POST.get('requires_water') == 'on'
        booking.require_stand_build = request.POST.get('require_stand_build') == 'on'
        booking.require_remove_side_walls = request.POST.get('require_remove_side_walls') == 'on'
        booking.require_floor_mat = request.POST.get('require_floor_mat') == 'on'
        booking.require_carpet = request.POST.get('require_carpet') == 'on'
        booking.require_extra_plugs = request.POST.get('require_extra_plugs') == 'on'
        booking.require_extra_lights = request.POST.get('require_extra_lights') == 'on'
        booking.special_requirements = request.POST.get('special_requirements', '')
        booking.side_wall_removal = request.POST.get('side_wall_removal', 'none')
        elec_dep = booking.event.electricity_deposit if booking.requires_power else Decimal('0')
        booking.electricity_deposit = elec_dep
        booking.subtotal, booking.vat_amount = booking_totals(booking.stall_price, elec_dep, booking.accessories_total, float(booking.event.vat_rate) / 100)
        booking.total_amount = booking.subtotal
        booking.balance_due = booking.total_amount - booking.amount_paid
        booking.save()
        from invoices.views import update_invoice_from_booking
        update_invoice_from_booking(booking)
        messages.success(request, 'Booking updated.')
    return redirect('booking_detail', pk=pk)


@login_required
def add_accessory(request, pk):
    booking = get_object_or_404(Booking, pk=pk, exhibitor=request.user)
    if request.method == 'POST':
        from decimal import Decimal
        from events.models import AccessoryType
        accessory = get_object_or_404(AccessoryType, pk=request.POST.get('accessory_id'))
        qty = int(request.POST.get('quantity', 1))
        from .models import BookingAccessory
        BookingAccessory.objects.create(booking=booking, accessory=accessory, quantity=qty, price=accessory.price)
        booking.accessories_total = sum(a.price * a.quantity for a in booking.accessories.all())
        booking.subtotal, booking.vat_amount = booking_totals(booking.stall_price, booking.electricity_deposit, booking.accessories_total, float(booking.event.vat_rate) / 100)
        booking.total_amount = booking.subtotal
        booking.balance_due = booking.total_amount - booking.amount_paid
        booking.save()
        from invoices.views import update_invoice_from_booking
        update_invoice_from_booking(booking)
        messages.success(request, f'Added {accessory.name} x{qty}')
    return redirect('booking_detail', pk=pk)


@login_required
def request_discount(request, pk):
    booking = get_object_or_404(Booking, pk=pk, exhibitor=request.user)
    if request.method == 'POST':
        from decimal import Decimal
        from .models import DiscountRequest
        from notifications.utils import send_discount_request, create_notification
        from django.contrib.auth import get_user_model
        discount_percent = Decimal(request.POST.get('discount_percent', '0'))
        discount_amount = (booking.total_amount * discount_percent / 100).quantize(Decimal('0.01'))
        dr = DiscountRequest.objects.create(
            booking=booking,
            requested_by=request.user,
            discount_percent=discount_percent,
            discount_amount=discount_amount,
            reason=request.POST.get('reason', ''),
        )
        send_discount_request(dr)
        User = get_user_model()
        for staff in User.objects.filter(is_staff=True, is_active=True):
            create_notification(
                staff, 'discount',
                f'Discount Request: {discount_percent}% - {booking.booking_reference}',
                f'{request.user.company_name or request.user.username} requested a {discount_percent}% discount (R{discount_amount:.2f}) on {booking.booking_reference}.',
                f'/erp/discounts/'
            )
        messages.success(request, 'Discount request submitted.')
    return redirect('booking_detail', pk=pk)


@login_required
def cancel_booking(request, pk):
    booking = get_object_or_404(Booking, pk=pk, exhibitor=request.user)
    if booking.status in ['pending', 'approved']:
        booking.status = 'cancelled'
        booking.save()
        booking.stall.status = 'available'
        booking.stall.save()
        messages.success(request, 'Booking cancelled.')
    else:
        messages.error(request, 'Cannot cancel this booking.')
    return redirect('my_bookings')


@login_required
def stand_3d_view(request, pk):
    booking = get_object_or_404(
        Booking.objects.select_related('exhibitor', 'stall__zone', 'event').prefetch_related('accessories__accessory'),
        pk=pk
    )
    if request.user != booking.exhibitor and not request.user.is_staff:
        from django.http import Http404
        raise Http404
    resolved_side = booking.side_wall_removal
    if booking.require_remove_side_walls and resolved_side == 'none':
        resolved_side = 'both'

    accessories_data = []
    for ba in booking.accessories.all():
        accessories_data.append({
            'id': ba.accessory.id,
            'name': ba.accessory.name,
            'quantity': ba.quantity,
        })

    return render(request, 'printouts/stand_3d_viewer.html', {
        'booking': booking,
        'resolved_side_wall': resolved_side,
        'accessories_json': json.dumps(accessories_data),
    })
