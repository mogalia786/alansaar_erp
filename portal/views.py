from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.db.models import Sum, Count, Q
from events.models import Event, FloorPlan, Zone, Stall, AccessoryType
import re, json, os
from bookings.models import Booking, DiscountRequest
from invoices.models import Invoice, Payment, Receipt, LedgerEntry
from accounts.models import User, Role, RolePermission
from providers.models import ServiceProvider, ServiceLog, Expense, RFQ, RFQCategory, Quotation, QuotationDocument, QuotationApproval
from django.utils import timezone
from decimal import Decimal
import json
import uuid
import os
from datetime import timedelta
from notifications.utils import (
    send_booking_confirmation, send_payment_received,
    send_discount_request, send_discount_decision,
    send_invoice_email
)
from accounting.auto_post import auto_post_invoice, auto_post_payment


def is_staff_user(user):
    return user.is_authenticated and (user.is_staff or user.user_type in ['staff', 'finance', 'director', 'admin', 'superadmin'])


def is_admin_user(user):
    return user.is_authenticated and user.user_type in ('admin', 'superadmin')


def erp_login_required(view_fn):
    """Require staff-level login, redirecting to /erp/login/ instead of /login/."""
    from django.contrib.auth.decorators import login_required
    from django.contrib.auth.views import redirect_to_login
    from functools import wraps

    @wraps(view_fn)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), login_url='/erp/login/')
        if not is_staff_user(request.user):
            return redirect_to_login(request.get_full_path(), login_url='/erp/login/')
        return view_fn(request, *args, **kwargs)
    return wrapper


def erp_section_required(section, action='view'):
    """Decorator that checks the user's role has permission for a section."""
    from functools import wraps
    def decorator(view_fn):
        @wraps(view_fn)
        @erp_login_required
        def wrapper(request, *args, **kwargs):
            if request.user.user_type in ('admin', 'superadmin'):
                return view_fn(request, *args, **kwargs)
            if not request.user.has_erp_permission(section, action):
                messages.error(request, f'Access denied: no {action} permission for {section}.')
                return redirect('erp:dashboard')
            return view_fn(request, *args, **kwargs)
        return wrapper
    return decorator


def erp_login(request):
    if request.user.is_authenticated and is_staff_user(request.user):
        return redirect('erp:dashboard')
    if request.method == 'POST':
        user = authenticate(request, username=request.POST['username'], password=request.POST['password'])
        if user and user.is_staff:
            login(request, user)
            return redirect('erp:dashboard')
        messages.error(request, 'Invalid staff credentials.')
    return render(request, 'portal/login.html')


def erp_logout(request):
    logout(request)
    return redirect('erp:login')


@erp_login_required
def erp_dashboard(request):
    ctx = {
        'active_events': Event.objects.filter(status__in=['published', 'ongoing']).count(),
        'total_bookings': Booking.objects.count(),
        'pending_bookings': Booking.objects.filter(status='pending').count(),
        'pending_payments': Payment.objects.filter(status='pending').count(),
        'unverified_exhibitors': User.objects.filter(user_type='exhibitor', is_verified=False).count(),
        'total_revenue': Invoice.objects.aggregate(s=Sum('amount_paid'))['s'] or 0,
        'recent_bookings': Booking.objects.select_related('exhibitor', 'event', 'stall').order_by('-booking_date')[:10],
    }
    return render(request, 'portal/dashboard.html', ctx)


@erp_section_required('events')
def erp_event_list(request):
    events = Event.objects.all().select_related('venue')
    return render(request, 'portal/event_list.html', {'events': events})


@erp_section_required('events')
def erp_event_detail(request, event_id):
    event = get_object_or_404(Event.objects.select_related('venue'), pk=event_id)
    stalls = event.stalls.select_related('zone').all()
    stalls_available = stalls.filter(status='available').count()
    floor_plan = getattr(event, 'floor_plan', None)
    zones = event.zones.all()
    return render(request, 'portal/event_detail.html', {
        'event': event, 'stalls': stalls, 'stalls_available': stalls_available,
        'floor_plan': floor_plan, 'zones': zones,
    })


@erp_section_required('floor_plan')
def erp_floor_plan(request, event_id):
    SCALE = 1
    event = get_object_or_404(Event, pk=event_id)
    floor_plan = getattr(event, 'floor_plan', None)
    stalls = event.stalls.all().select_related('zone')
    zones = list(event.zones.all().values('id', 'name', 'zone_type', 'color'))
    stalls_data = [{
        'id': s.id, 'name': s.name, 'x': s.position_x, 'y': s.position_y,
        'w': s.width, 'h': s.height, 'status': s.status,
        'price': float(s.total_price), 'is_corner': s.is_corner,
        'has_water': s.has_water, 'zone': s.zone_id,
        'size_sqm': float(s.size_sqm),
    } for s in stalls]
    walkways_raw = json.loads(floor_plan.walkways_json) if floor_plan and floor_plan.walkways_json else []
    walkways_data = walkways_raw
    exits_raw = json.loads(floor_plan.exit_markers_json) if floor_plan and floor_plan.exit_markers_json else []
    exits_data = exits_raw

    svg_content = ''
    fp_w, fp_h = 502485, 721189
    paths_to_try = ['floor_plans/dec_full_floor_plan.svg', 'dec_full_floor_plan.svg']
    raw = None
    for svg_rel_path in paths_to_try:
        if raw is not None:
            break
        try:
            from django.core.files.storage import default_storage
            print(f'portal SVG: trying storage path={svg_rel_path}, storage={type(default_storage).__name__}')
            if default_storage.exists(svg_rel_path):
                f = default_storage.open(svg_rel_path)
                raw = f.read()
                f.close()
                if isinstance(raw, bytes):
                    raw = raw.decode('utf-8', errors='replace')
                print(f'portal SVG: loaded from storage path={svg_rel_path}, size={len(raw)}')
        except Exception as e:
            print(f'portal SVG: storage failed for {svg_rel_path}: {e}')
    for svg_rel_path in paths_to_try:
        if raw is not None:
            break
        try:
            import requests as http_requests
            r2_domain = getattr(settings, 'AWS_S3_CUSTOM_DOMAIN', '')
            if r2_domain:
                url = f"https://{r2_domain}/{svg_rel_path}"
                print(f'portal SVG: trying public URL={url}')
                resp = http_requests.get(url, timeout=30)
                if resp.status_code == 200:
                    raw = resp.text
                    print(f'portal SVG: loaded from public URL, size={len(raw)}')
                else:
                    print(f'portal SVG: public URL returned {resp.status_code}')
        except Exception as e:
            print(f'portal SVG: public URL failed: {e}')
    if raw is None:
        for svg_rel_path in paths_to_try:
            full_svg = os.path.join(str(settings.MEDIA_ROOT), svg_rel_path)
            if os.path.exists(full_svg):
                with open(full_svg, 'r', encoding='utf-8') as f:
                    raw = f.read()
                print(f'portal SVG: loaded from local file={full_svg}')
                break
    if raw is None:
        print('portal SVG: all paths failed')
    if raw:
        try:
            vb = re.search(r'viewBox="([^"]+)"', raw)
            if vb:
                parts = vb.group(1).split()
                fp_w = int(float(parts[2]))
                fp_h = int(float(parts[3]))
            raw = raw.replace('overflow="hidden"', 'overflow="visible"')
            svg_tag = re.search(r'<svg\b[^>]*>', raw)
            if svg_tag and 'overflow=' not in svg_tag.group():
                raw = raw[:svg_tag.end() - 1] + ' overflow="visible">' + raw[svg_tag.end():]
            raw = re.sub(r'<svg\b', '<svg class="fp-svg"', raw, count=1)
            raw = re.sub(r'width="[^"]*"', f'width="{fp_w}"', raw)
            raw = re.sub(r'height="[^"]*"', f'height="{fp_h}"', raw)
            svg_content = raw
            print(f'portal SVG: processed OK, svg_content len={len(svg_content)}')
        except Exception as e:
            print(f'portal SVG: processing FAILED: {e}')

    return render(request, 'portal/floor_plan.html', {
        'event': event, 'floor_plan': floor_plan,
        'zones': json.dumps(zones), 'stalls_data': json.dumps(stalls_data),
        'walkways_data': json.dumps(walkways_data),
        'exits_data': json.dumps(exits_data),
        'svg_content': svg_content,
        'svg_w': fp_w,
        'svg_h': fp_h,
        'scale': SCALE,
    })


@erp_section_required('floor_plan')
def floor_plan_frame(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    floor_plan = getattr(event, 'floor_plan', None)
    svg_content = ''
    fp_w, fp_h = 4000, 3000
    paths_to_try = ['floor_plans/dec_full_floor_plan.svg', 'dec_full_floor_plan.svg']
    raw = None
    for svg_rel_path in paths_to_try:
        if raw is not None:
            break
        try:
            from django.core.files.storage import default_storage
            print(f'frame SVG: trying storage path={svg_rel_path}, storage={type(default_storage).__name__}')
            if default_storage.exists(svg_rel_path):
                f = default_storage.open(svg_rel_path)
                raw = f.read()
                f.close()
                if isinstance(raw, bytes):
                    raw = raw.decode('utf-8', errors='replace')
                print(f'frame SVG: loaded from storage path={svg_rel_path}, size={len(raw)}')
        except Exception as e:
            print(f'frame SVG: storage failed for {svg_rel_path}: {e}')
    for svg_rel_path in paths_to_try:
        if raw is not None:
            break
        try:
            import requests as http_requests
            r2_domain = getattr(settings, 'AWS_S3_CUSTOM_DOMAIN', '')
            if r2_domain:
                url = f"https://{r2_domain}/{svg_rel_path}"
                print(f'frame SVG: trying public URL={url}')
                resp = http_requests.get(url, timeout=30)
                if resp.status_code == 200:
                    raw = resp.text
                    print(f'frame SVG: loaded from public URL, size={len(raw)}')
                else:
                    print(f'frame SVG: public URL returned {resp.status_code}')
        except Exception as e:
            print(f'frame SVG: public URL failed: {e}')
    if raw is None:
        for svg_rel_path in paths_to_try:
            full_svg = os.path.join(str(settings.MEDIA_ROOT), svg_rel_path)
            if os.path.exists(full_svg):
                with open(full_svg, 'r', encoding='utf-8') as f:
                    raw = f.read()
                print(f'frame SVG: loaded from local file={full_svg}')
                break
    if raw is None:
        print('frame SVG: all paths failed')
    if raw:
        try:
            vb = re.search(r'viewBox="([^"]+)"', raw)
            if vb:
                parts = vb.group(1).split()
                fp_w = int(float(parts[2]))
                fp_h = int(float(parts[3]))
            raw = raw.replace('overflow="hidden"', 'overflow="visible"')
            raw = raw.replace('<svg', '<svg class="fp-svg"')
            svg_content = raw
        except Exception:
            pass
    return render(request, 'portal/floor_plan_frame.html', {
        'floor_plan': floor_plan,
        'svg_content': svg_content,
        'svg_w': fp_w,
        'svg_h': fp_h,
    })


@erp_login_required
def upload_floor_plan(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    if request.method == 'POST':
        image = request.FILES.get('image')
        if image:
            FloorPlan.objects.update_or_create(event=event, defaults={'image': image})
            messages.success(request, 'Floor plan uploaded.')
        else:
            messages.error(request, 'No image selected.')
        return redirect('erp:event_detail', event_id=event_id)
    return redirect('erp:event_detail', event_id=event_id)


@erp_login_required
def create_stall(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    if request.method == 'POST':
        last = event.stalls.order_by('-id').first()
        num = (last.id % 100 + 1) if last else 1
        stall = Stall.objects.create(
            event=event,
            name=f"S{num:02d}",
            position_x=int(request.POST.get('x', 0)),
            position_y=int(request.POST.get('y', 0)),
            width=int(request.POST.get('width', 180)),
            height=int(request.POST.get('height', 180)),
            size_sqm=Decimal(request.POST.get('size_sqm', 9)),
            base_price=Decimal(request.POST.get('base_price', 5000)),
        )
        messages.success(request, f'Stall {stall.name} created.')
        return redirect('erp:event_detail', event_id=event_id)
    return redirect('erp:event_detail', event_id=event_id)


@erp_login_required
def save_floor_plan_meta(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    if request.method == 'POST':
        data = json.loads(request.body)
        floor_plan, _ = FloorPlan.objects.get_or_create(event=event)
        if 'walkways' in data:
            floor_plan.walkways_json = json.dumps(data['walkways'])
        if 'exits' in data:
            floor_plan.exit_markers_json = json.dumps(data['exits'])
        floor_plan.save()
        return JsonResponse({'ok': True})
    return JsonResponse({'ok': False}, status=405)


@erp_login_required
def save_stalls(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    if request.method == 'POST':
        data = json.loads(request.body)
        updated = 0
        created = 0
        for item in data:
            pk = item.get('id')
            stall = Stall.objects.filter(pk=pk, event=event).first() if pk else None
            if stall:
                stall.position_x = item['x']
                stall.position_y = item['y']
                stall.width = item['w']
                stall.height = item['h']
                stall.size_sqm = Decimal(str(item.get('size_sqm', stall.size_sqm)))
                stall.base_price = Decimal(str(item.get('base_price', stall.base_price)))
                stall.corner_premium = Decimal(str(item.get('corner_premium', '0')))
                stall.is_corner = item.get('is_corner', False)
                stall.has_water = item.get('has_water', False)
                stall.zone_id = item.get('zone')
                stall.save()
                updated += 1
            else:
                name = item.get('name', 'NEW')
                existing = Stall.objects.filter(event=event, name=name).first()
                if existing:
                    existing.position_x = item['x']
                    existing.position_y = item['y']
                    existing.width = item['w']
                    existing.height = item['h']
                    existing.size_sqm = Decimal(str(item.get('size_sqm', existing.size_sqm)))
                    existing.base_price = Decimal(str(item.get('base_price', existing.base_price)))
                    existing.corner_premium = Decimal(str(item.get('corner_premium', '0')))
                    existing.is_corner = item.get('is_corner', False)
                    existing.has_water = item.get('has_water', False)
                    existing.zone_id = item.get('zone')
                    existing.save()
                    updated += 1
                else:
                    prefix = item.get('prefix', 'S')
                    zone_id = item.get('zone')
                    Stall.objects.create(
                        event=event, name=name, stall_prefix=prefix,
                        position_x=item['x'], position_y=item['y'],
                        width=item['w'], height=item['h'],
                        size_sqm=Decimal(str(item.get('size_sqm', 9))),
                        base_price=Decimal(str(item.get('base_price', 5000))),
                        corner_premium=Decimal(str(item.get('corner_premium', '0'))),
                        is_corner=item.get('is_corner', False),
                        has_water=item.get('has_water', False),
                        zone_id=zone_id,
                    )
                    created += 1
        return JsonResponse({'ok': True, 'updated': updated, 'created': created})
    return JsonResponse({'ok': False}, status=405)


@erp_section_required('bookings')
def erp_booking_list(request):
    bookings = Booking.objects.all().select_related('exhibitor', 'event', 'stall')
    status = request.GET.get('status')
    if status:
        bookings = bookings.filter(status=status)
    return render(request, 'portal/booking_list.html', {'bookings': bookings})


@erp_section_required('bookings')
def erp_booking_detail(request, pk):
    booking = get_object_or_404(Booking.objects.select_related('exhibitor', 'event', 'stall', 'stall__zone'), pk=pk)
    invoices = booking.invoices.all()
    payments = booking.payments.all()
    discount_requests = booking.discount_requests.all()
    return render(request, 'portal/booking_detail.html', {
        'booking': booking, 'invoices': invoices,
        'payments': payments, 'discount_requests': discount_requests,
    })


@erp_login_required
def approve_booking(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    if booking.status == 'pending':
        booking.status = 'approved'
        booking.approved_date = timezone.now()
        booking.save()
        booking.stall.status = 'reserved'
        booking.stall.save()
        messages.success(request, f'Booking {booking.booking_reference} approved.')
    return redirect('erp:booking_detail', pk=pk)


@erp_login_required
def reject_booking(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    if booking.status == 'pending':
        booking.status = 'rejected'
        booking.save()
        booking.stall.status = 'available'
        booking.stall.save()
        messages.success(request, f'Booking {booking.booking_reference} rejected.')
    return redirect('erp:booking_detail', pk=pk)


@erp_login_required
def confirm_booking(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    if booking.status == 'approved':
        booking.status = 'confirmed'
        booking.confirmed_date = timezone.now()
        booking.payment_status = 'paid'
        booking.save()
        booking.stall.status = 'confirmed'
        booking.stall.save()
        messages.success(request, f'Booking {booking.booking_reference} confirmed.')
        send_booking_confirmation(booking)
    return redirect('erp:booking_detail', pk=pk)


@erp_section_required('invoices')
def erp_invoice_list(request):
    invoices = Invoice.objects.all().select_related('exhibitor', 'booking')
    return render(request, 'portal/invoice_list.html', {'invoices': invoices})


@erp_login_required
def create_invoice(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id)
    if request.method == 'POST':
        inv = Invoice.objects.create(
            invoice_number=f"INV-{uuid.uuid4().hex[:8].upper()}",
            booking=booking,
            exhibitor=booking.exhibitor,
            amount_excl=booking.subtotal,
            vat_amount=booking.vat_amount,
            amount_incl=booking.total_amount,
            balance_due=booking.total_amount,
            status='sent',
            issue_date=timezone.now().date(),
            due_date=timezone.now().date() + timezone.timedelta(days=30),
        )
        LedgerEntry.objects.create(
            exhibitor=booking.exhibitor, booking=booking,
            entry_type='invoice', description=f'Stall booking - {booking.stall.name}',
            reference=inv.invoice_number,
            debit=inv.amount_incl, credit=0, balance=inv.amount_incl,
            entry_date=inv.issue_date,
        )
        messages.success(request, f'Invoice {inv.invoice_number} created.')
        auto_post_invoice(inv, created_by=request.user)
        send_invoice_email(inv, 'created')
        return redirect('erp:booking_detail', pk=booking_id)
    return redirect('erp:booking_detail', pk=booking_id)


@erp_section_required('payments')
def erp_payment_list(request):
    payments = Payment.objects.all().select_related('invoice', 'booking__exhibitor')
    status = request.GET.get('status')
    if status:
        payments = payments.filter(status=status)
    return render(request, 'portal/payment_list.html', {'payments': payments})


@erp_login_required
def verify_payment(request, pk):
    payment = get_object_or_404(Payment, pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action', 'verify')
        if action == 'verify':
            payment.status = 'verified'
            payment.verified_by = request.user
            payment.verified_at = timezone.now()
            payment.receipt_number = f"RCT-{uuid.uuid4().hex[:8].upper()}"
            payment.save()
            inv = payment.invoice
            from invoices.views import update_invoice_from_booking
            inv = update_invoice_from_booking(inv.booking)
            booking = inv.booking
            booking.amount_paid = inv.amount_paid
            booking.balance_due = inv.balance_due
            if inv.balance_due <= 0:
                booking.payment_status = 'paid'
            booking.save()
            receipt = Receipt.objects.create(
                receipt_number=payment.receipt_number,
                payment=payment,
                exhibitor=payment.booking.exhibitor,
                amount=payment.amount,
                payment_method=payment.payment_method,
                reference_number=payment.reference_number,
                issue_date=timezone.now().date(),
            )
            LedgerEntry.objects.create(
                exhibitor=payment.booking.exhibitor,
                booking=payment.booking,
                entry_type='payment',
                description=f'Payment received - {inv.invoice_number}',
                reference=receipt.receipt_number,
                debit=0, credit=payment.amount,
                balance=inv.balance_due,
                entry_date=timezone.now().date(),
            )
            auto_post_payment(payment, created_by=request.user)
            from notifications.utils import send_payment_verified
            send_payment_verified(payment, receipt)
            messages.success(request, f'Payment verified. Receipt: {receipt.receipt_number}.')
        elif action == 'reject':
            payment.status = 'rejected'
            payment.save()
            messages.warning(request, 'Payment rejected.')
    return redirect('erp:payment_list')


@erp_section_required('payments')
def collect_cash(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id)
    invoice = booking.invoices.first()
    if not invoice:
        messages.error(request, 'No invoice found for this booking.')
        return redirect('erp:booking_detail', pk=booking_id)
    if request.method == 'POST':
        amount = Decimal(request.POST.get('amount', '0'))
        ref = request.POST.get('reference_number', booking.stall.name)
        notes = request.POST.get('notes', '')
        if amount <= 0:
            messages.error(request, 'Amount must be greater than zero.')
            return redirect('erp:collect_cash', booking_id=booking_id)
        payment = Payment.objects.create(
            invoice=invoice,
            booking=booking,
            amount=amount,
            payment_method='cash',
            reference_number=ref,
            status='verified',
            verified_by=request.user,
            verified_at=timezone.now(),
            notes=notes,
        )
        payment.receipt_number = f"RCT-{uuid.uuid4().hex[:8].upper()}"
        payment.save()
        from invoices.views import update_invoice_from_booking
        inv = update_invoice_from_booking(booking)
        booking.amount_paid = inv.amount_paid
        booking.balance_due = inv.balance_due
        if inv.balance_due <= 0:
            booking.payment_status = 'paid'
        elif inv.amount_paid > 0:
            booking.payment_status = 'partial'
        booking.save()
        receipt = Receipt.objects.create(
            receipt_number=payment.receipt_number,
            payment=payment,
            exhibitor=booking.exhibitor,
            amount=payment.amount,
            payment_method='cash',
            reference_number=ref,
            issue_date=timezone.now().date(),
            notes=notes,
        )
        LedgerEntry.objects.create(
            exhibitor=booking.exhibitor,
            booking=booking,
            entry_type='payment',
            description=f'Cash payment - {invoice.invoice_number}',
            reference=receipt.receipt_number,
            debit=0, credit=payment.amount,
            balance=inv.balance_due,
            entry_date=timezone.now().date(),
        )
        messages.success(request, f'Cash payment of R{amount:.2f} recorded. Receipt: {receipt.receipt_number}')
        return redirect('erp:booking_detail', pk=booking_id)
    from decimal import Decimal as D
    verified_total = invoice.payments.filter(status='verified').aggregate(s=Sum('amount'))['s'] or D('0')
    context = {
        'booking': booking,
        'invoice': invoice,
        'balance_due': invoice.amount_incl - verified_total,
        'verified_total': verified_total,
    }
    return render(request, 'portal/collect_cash.html', context)


@erp_section_required('payments')
def print_payments_receipt(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id)
    invoice = booking.invoices.first()
    payments = Payment.objects.filter(
        booking=booking, status='verified'
    ).select_related('invoice').order_by('payment_date')
    receipt = None
    if payments.exists():
        last_payment = payments.first()
        receipt = Receipt.objects.filter(payment=last_payment).first()
    total_paid = payments.aggregate(s=Sum('amount'))['s'] or Decimal('0')
    return render(request, 'printouts/payments_receipt.html', {
        'booking': booking,
        'invoice': invoice,
        'payments': payments,
        'receipt': receipt,
        'total_paid': total_paid,
    })


@erp_section_required('exhibitors')
def erp_exhibitor_list(request):
    exhibitors = User.objects.filter(user_type='exhibitor')
    q = request.GET.get('q')
    if q:
        exhibitors = exhibitors.filter(Q(company_name__icontains=q) | Q(email__icontains=q) | Q(username__icontains=q))
    return render(request, 'portal/exhibitor_list.html', {'exhibitors': exhibitors})


@erp_login_required
def erp_accessory_list(request):
    accessories = AccessoryType.objects.all()
    return render(request, 'portal/accessory_list.html', {'accessories': accessories})


@erp_login_required
def add_accessory(request):
    if request.method == 'POST':
        AccessoryType.objects.create(
            name=request.POST['name'],
            description=request.POST.get('description', ''),
            price=Decimal(request.POST['price']),
            unit=request.POST.get('unit', 'per unit'),
        )
        messages.success(request, 'Accessory added.')
    return redirect('erp:accessory_list')


@erp_login_required
def erp_discount_list(request):
    discounts = DiscountRequest.objects.all().select_related('booking', 'requested_by')
    return render(request, 'portal/discount_list.html', {'discounts': discounts})


@erp_login_required
def approve_discount(request, pk):
    dr = get_object_or_404(DiscountRequest, pk=pk)
    if dr.status == 'pending':
        dr.approved_by_first = request.user
        dr.status = 'approved_by_first'
        dr.save()
        # Notify remaining directors that first approval was given
        from notifications.utils import get_director_emails, send_html_email
        remaining = [e for e in get_director_emails() if e != request.user.email]
        if remaining:
            context = {
                'dr': dr,
                'booking': dr.booking,
                'approved_by': request.user,
                'site_name': settings.SITE_NAME,
                'site_url': settings.SITE_URL,
            }
            send_html_email(
                f'First Approval Received - {dr.discount_percent}% - {dr.booking.booking_reference}',
                'emails/discount_first_approval.html', context, remaining,
            )
        messages.success(request, f'Discount request approved by {request.user.username} (1/2). Awaiting second approval.')
    elif dr.status == 'approved_by_first':
        dr.approved_by_second = request.user
        dr.status = 'approved'
        dr.booking.subtotal -= dr.discount_amount
        dr.booking.vat_amount = dr.booking.subtotal * Decimal('0.15')
        dr.booking.total_amount = dr.booking.subtotal + dr.booking.vat_amount
        dr.booking.balance_due = dr.booking.total_amount - dr.booking.amount_paid
        dr.booking.save()
        dr.save()
        # Auto-post accounting adjustment
        from accounting.auto_post import auto_post_discount
        auto_post_discount(dr.booking, dr.discount_amount, request.user)
        send_discount_decision(dr)
        messages.success(request, f'Discount fully approved by {request.user.username} (2/2). Totals updated.')
    return redirect('erp:discount_list')


@erp_login_required
def reject_discount(request, pk):
    dr = get_object_or_404(DiscountRequest, pk=pk)
    if dr.status in ['pending', 'approved_by_first']:
        dr.status = 'rejected'
        dr.rejected_by = request.user
        dr.save()
        send_discount_decision(dr)
        messages.success(request, f'Discount request rejected by {request.user.username}.')
    return redirect('erp:discount_list')


@erp_login_required
def print_stand_spec(request, booking_id):
    booking = get_object_or_404(Booking.objects.select_related('exhibitor', 'event', 'stall', 'stall__zone'), pk=booking_id)
    return render(request, 'printouts/stand_spec.html', {'booking': booking})


@erp_login_required
def print_electrician(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    if request.method == 'POST':
        pk = request.POST.get('booking_id')
        action = request.POST.get('action')
        if pk and action:
            b = get_object_or_404(Booking, pk=pk)
            if action == 'complete_electrical':
                b.electrical_completed = True
                b.save()
                messages.success(request, f'{b.booking_reference} marked electrical complete.')
            elif action == 'reset_electrical':
                b.electrical_completed = False
                b.save()
                messages.success(request, f'{b.booking_reference} electrical reset.')
        return redirect('erp:print_electrician', event_id=event_id)
    bookings = event.bookings.all().select_related('stall', 'exhibitor').prefetch_related('accessories__accessory')
    return render(request, 'printouts/electrician.html', {'event': event, 'bookings': bookings})


@erp_login_required
def print_stand_builder(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    if request.method == 'POST':
        pk = request.POST.get('booking_id')
        action = request.POST.get('action')
        if pk and action:
            b = get_object_or_404(Booking, pk=pk)
            if action == 'complete_build':
                b.stand_build_completed = True
                b.save()
                messages.success(request, f'{b.booking_reference} marked build complete.')
            elif action == 'reset_build':
                b.stand_build_completed = False
                b.save()
                messages.success(request, f'{b.booking_reference} build reset.')
        return redirect('erp:print_stand_builder', event_id=event_id)
    bookings = event.bookings.all().select_related('stall__zone', 'exhibitor')
    total_tables = sum(b.stall.num_tables for b in bookings if b.stall)
    total_chairs = sum(b.stall.num_chairs for b in bookings if b.stall)
    return render(request, 'printouts/stand_builder.html', {
        'event': event, 'bookings': bookings,
        'total_tables': total_tables, 'total_chairs': total_chairs,
    })


@erp_login_required
def print_accessories(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    bookings = event.bookings.all().prefetch_related('accessories__accessory', 'stall')
    return render(request, 'printouts/accessories.html', {'event': event, 'bookings': bookings})


@erp_section_required('accounting')
def erp_statement(request, exhibitor_id):
    exhibitor = get_object_or_404(User, pk=exhibitor_id, user_type='exhibitor')
    entries = LedgerEntry.objects.filter(exhibitor=exhibitor).select_related('booking').order_by('entry_date', 'created_at')
    total_invoiced = entries.filter(entry_type='invoice').aggregate(s=Sum('debit'))['s'] or 0
    total_paid = entries.filter(entry_type='payment').aggregate(s=Sum('credit'))['s'] or 0
    total_debits = entries.aggregate(s=Sum('debit'))['s'] or 0
    total_credits = entries.aggregate(s=Sum('credit'))['s'] or 0
    closing_balance = total_debits - total_credits
    outstanding = total_invoiced - total_paid
    today = timezone.now().date()
    aging_current = aging_30 = aging_60 = aging_90 = Decimal('0')
    for inv in Invoice.objects.filter(exhibitor=exhibitor, status__in=['sent', 'partial', 'overdue']):
        bal = inv.balance_due
        if bal > 0:
            days = (today - inv.due_date).days
            if days <= 0: aging_current += bal
            elif days <= 30: aging_30 += bal
            elif days <= 60: aging_60 += bal
            else: aging_90 += bal
    return render(request, 'printouts/statement.html', {
        'exhibitor': exhibitor, 'ledger': entries,
        'total_invoiced': total_invoiced, 'total_paid': total_paid,
        'outstanding': outstanding, 'overdue': aging_30 + aging_60 + aging_90,
        'total_debits': total_debits, 'total_credits': total_credits,
        'closing_balance': closing_balance,
        'aging_current': aging_current, 'aging_30': aging_30,
        'aging_60': aging_60, 'aging_90': aging_90,
    })


@erp_section_required('reports')
def erp_reports(request):
    events = Event.objects.all()
    report_data = []
    for event in events:
        total_bookings = event.bookings.count()
        confirmed = event.bookings.filter(status='confirmed').count()
        total_rev = event.bookings.aggregate(s=Sum('total_amount'))['s'] or 0
        paid_rev = event.bookings.filter(payment_status='paid').aggregate(s=Sum('total_amount'))['s'] or 0
        report_data.append({
            'event': event,
            'total_bookings': total_bookings,
            'confirmed': confirmed,
            'total_revenue': total_rev,
            'paid_revenue': paid_rev,
            'outstanding': total_rev - paid_rev,
        })
    return render(request, 'portal/reports.html', {'report_data': report_data})


@erp_section_required('expenses')
def erp_expense_list(request):
    expenses = Expense.objects.all().select_related('provider', 'created_by')
    status = request.GET.get('status')
    if status:
        expenses = expenses.filter(status=status)
    return render(request, 'portal/expense_list.html', {'expenses': expenses})


@erp_login_required
def erp_expense_create(request):
    providers = ServiceProvider.objects.filter(is_active=True)
    if request.method == 'POST':
        from decimal import Decimal
        provider_id = request.POST.get('provider')
        provider = get_object_or_404(ServiceProvider, pk=provider_id) if provider_id else None
        excl = Decimal(request.POST.get('amount_excl', '0'))
        vat = excl * Decimal('0.15')
        incl = excl + vat
        expense = Expense.objects.create(
            provider=provider,
            description=request.POST.get('description', ''),
            category=request.POST.get('category', 'other'),
            amount_excl=excl,
            vat_amount=vat,
            amount_incl=incl,
            balance_due=incl,
            expense_date=timezone.now().date(),
            due_date=request.POST.get('due_date') or None,
            notes=request.POST.get('notes', ''),
            created_by=request.user,
        )
        from accounting.auto_post import auto_post_expense
        auto_post_expense(expense, created_by=request.user)
        messages.success(request, f'Expense created: {expense.description[:50]}')
        return redirect('erp:expense_list')
    return render(request, 'portal/expense_form.html', {'providers': providers, 'edit': False})


@erp_login_required
def erp_expense_edit(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    providers = ServiceProvider.objects.filter(is_active=True)
    if request.method == 'POST':
        from decimal import Decimal
        provider_id = request.POST.get('provider')
        expense.provider = get_object_or_404(ServiceProvider, pk=provider_id) if provider_id else None
        expense.description = request.POST.get('description', '')
        expense.category = request.POST.get('category', 'other')
        expense.notes = request.POST.get('notes', '')
        expense.save()
        messages.success(request, 'Expense updated.')
        return redirect('erp:expense_list')
    return render(request, 'portal/expense_form.html', {'expense': expense, 'providers': providers, 'edit': True})


@erp_login_required
def erp_expense_pay(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    if request.method == 'POST':
        from decimal import Decimal
        amount = Decimal(request.POST.get('amount', '0'))
        expense.amount_paid += amount
        expense.balance_due = expense.amount_incl - expense.amount_paid
        expense.payment_reference = request.POST.get('payment_reference', '')
        if expense.balance_due <= 0:
            expense.status = 'paid'
            expense.paid_date = timezone.now().date()
        elif expense.amount_paid > 0:
            expense.status = 'partial'
        expense.save()
        from accounting.auto_post import auto_post_expense_payment
        auto_post_expense_payment(expense, amount, created_by=request.user)
        messages.success(request, f'Payment of R{amount:.2f} recorded for expense.')
        return redirect('erp:expense_list')
    return render(request, 'portal/expense_pay.html', {'expense': expense})


@erp_login_required
def erp_provider_ledger(request, pk):
    """Show a provider's full ledger: expenses (liability) + payments made."""
    provider = get_object_or_404(ServiceProvider, pk=pk)
    expenses = Expense.objects.filter(provider=provider).order_by('expense_date')
    total_billed = sum(e.amount_incl for e in expenses)
    total_paid = sum(e.amount_paid for e in expenses)
    balance_due = total_billed - total_paid
    return render(request, 'portal/provider_ledger.html', {
        'provider': provider,
        'expenses': expenses,
        'total_billed': total_billed,
        'total_paid': total_paid,
        'balance_due': balance_due,
    })


@erp_section_required('providers')
def erp_provider_list(request):
    providers = ServiceProvider.objects.all()
    q = request.GET.get('q')
    if q:
        providers = providers.filter(Q(company_name__icontains=q) | Q(contact_person__icontains=q))
    return render(request, 'portal/provider_list.html', {'providers': providers})


@erp_login_required
def erp_provider_create(request):
    if request.method == 'POST':
        from django.contrib.auth.hashers import make_password
        import uuid
        email = request.POST.get('email', '')
        manual_pwd = request.POST.get('password', '').strip()
        pwd = manual_pwd if manual_pwd else str(uuid.uuid4().hex[:12])
        provider = ServiceProvider.objects.create(
            email=email,
            password=make_password(pwd),
            company_name=request.POST.get('company_name', ''),
            company_type=request.POST.get('company_type', 'ptyltd'),
            registration_number=request.POST.get('registration_number', ''),
            vat_number=request.POST.get('vat_number', ''),
            service_type=request.POST.get('service_type', 'other'),
            phone=request.POST.get('phone', ''),
            alternative_phone=request.POST.get('alternative_phone', ''),
            contact_person=request.POST.get('contact_person', ''),
            physical_address=request.POST.get('physical_address', ''),
            postal_address=request.POST.get('postal_address', ''),
            bank_name=request.POST.get('bank_name', ''),
            bank_branch=request.POST.get('bank_branch', ''),
            bank_account_number=request.POST.get('bank_account_number', ''),
            bank_account_type=request.POST.get('bank_account_type', 'business'),
            bank_branch_code=request.POST.get('bank_branch_code', ''),
        )
        msg = f'Provider {provider.company_name} created.'
        if not manual_pwd:
            msg += f' Auto-generated password: {pwd}'
        messages.success(request, msg)
        return redirect('erp:provider_list')
    return render(request, 'portal/provider_form.html', {'edit': False})


@erp_login_required
def erp_provider_edit(request, pk):
    provider = get_object_or_404(ServiceProvider, pk=pk)
    if request.method == 'POST':
        from django.contrib.auth.hashers import make_password
        provider.company_name = request.POST.get('company_name', '')
        provider.company_type = request.POST.get('company_type', 'ptyltd')
        provider.registration_number = request.POST.get('registration_number', '')
        provider.vat_number = request.POST.get('vat_number', '')
        provider.service_type = request.POST.get('service_type', 'other')
        provider.phone = request.POST.get('phone', '')
        provider.alternative_phone = request.POST.get('alternative_phone', '')
        provider.contact_person = request.POST.get('contact_person', '')
        provider.physical_address = request.POST.get('physical_address', '')
        provider.postal_address = request.POST.get('postal_address', '')
        provider.bank_name = request.POST.get('bank_name', '')
        provider.bank_branch = request.POST.get('bank_branch', '')
        provider.bank_account_number = request.POST.get('bank_account_number', '')
        provider.bank_account_type = request.POST.get('bank_account_type', 'business')
        provider.bank_branch_code = request.POST.get('bank_branch_code', '')
        provider.is_verified = request.POST.get('is_verified') == 'on'
        new_pwd = request.POST.get('new_password', '').strip()
        if new_pwd:
            provider.password = make_password(new_pwd)
        provider.save()
        msg = 'Provider updated.'
        if new_pwd:
            msg += f' New password set.'
        messages.success(request, msg)
        return redirect('erp:provider_detail', pk=provider.pk)
    return render(request, 'portal/provider_form.html', {'provider': provider, 'edit': True})


@erp_login_required
def erp_provider_detail(request, pk):
    provider = get_object_or_404(ServiceProvider, pk=pk)
    logs = provider.service_logs.all()
    expenses = provider.expenses.all()
    return render(request, 'portal/provider_detail.html', {
        'provider': provider, 'logs': logs, 'expenses': expenses,
    })


@erp_login_required
def erp_provider_add_log(request, pk):
    provider = get_object_or_404(ServiceProvider, pk=pk)
    if request.method == 'POST':
        from decimal import Decimal
        ServiceLog.objects.create(
            provider=provider,
            event_id=request.POST.get('event_id') or None,
            description=request.POST.get('description', ''),
            service_date=request.POST.get('service_date') or timezone.now().date(),
            amount_charged=Decimal(request.POST.get('amount_charged', '0')),
            notes=request.POST.get('notes', ''),
        )
        messages.success(request, 'Service log added.')
        return redirect('erp:provider_detail', pk=pk)
    from events.models import Event
    events = Event.objects.all()
    return render(request, 'portal/provider_log_form.html', {'provider': provider, 'events': events})


@erp_section_required('users')
def erp_user_list(request):
    users = User.objects.all().select_related('role')
    q = request.GET.get('q')
    ut = request.GET.get('user_type')
    if q:
        users = users.filter(Q(username__icontains=q) | Q(email__icontains=q) | Q(company_name__icontains=q))
    if ut:
        users = users.filter(user_type=ut)
    return render(request, 'portal/user_list.html', {'users': users, 'user_types': User.USER_TYPES})


@erp_login_required
def erp_user_create(request):
    roles = Role.objects.filter(is_active=True)
    if request.method == 'POST':
        utype = request.POST.get('user_type', 'staff')
        is_staff_val = utype in ('staff', 'finance', 'director', 'admin', 'superadmin')
        user = User.objects.create_user(
            username=request.POST.get('username', ''),
            email=request.POST.get('email', ''),
            password=request.POST.get('password', 'changeme123'),
            user_type=utype,
            phone=request.POST.get('phone', ''),
            company_name=request.POST.get('company_name', ''),
            is_staff=is_staff_val,
            role_id=request.POST.get('role_id') or None,
        )
        messages.success(request, f'User {user.username} created.')
        return redirect('erp:user_list')
    return render(request, 'portal/user_form.html', {'roles': roles, 'edit': False})


@erp_login_required
def erp_user_edit(request, pk):
    user = get_object_or_404(User, pk=pk)
    roles = Role.objects.filter(is_active=True)
    if request.method == 'POST':
        utype = request.POST.get('user_type', 'staff')
        user.email = request.POST.get('email', '')
        user.user_type = utype
        user.is_staff = utype in ('staff', 'finance', 'director', 'admin', 'superadmin')
        user.phone = request.POST.get('phone', '')
        user.company_name = request.POST.get('company_name', '')
        user.is_active = request.POST.get('is_active') == 'on'
        user.role_id = request.POST.get('role_id') or None
        pwd = request.POST.get('password', '')
        if pwd:
            user.set_password(pwd)
        user.save()
        messages.success(request, f'User {user.username} updated.')
        return redirect('erp:user_list')
    return render(request, 'portal/user_form.html', {'edit_user': user, 'roles': roles, 'edit': True})


@erp_login_required
@user_passes_test(is_admin_user)
def erp_role_list(request):
    roles = Role.objects.all().prefetch_related('permissions')
    return render(request, 'portal/role_list.html', {'roles': roles})


@erp_login_required
@user_passes_test(is_admin_user)
def erp_role_create(request):
    if request.method == 'POST':
        role = Role.objects.create(
            name=request.POST.get('name', ''),
            description=request.POST.get('description', ''),
        )
        # Create default permissions for all sections
        for section, _ in RolePermission.SECTIONS:
            RolePermission.objects.create(
                role=role, section=section,
                can_view=True, can_create=False,
                can_edit=False, can_delete=False,
            )
        messages.success(request, f'Role {role.name} created. Configure permissions below.')
        return redirect('erp:role_edit', pk=role.pk)
    return render(request, 'portal/role_form.html', {'edit': False})


@erp_login_required
@user_passes_test(is_admin_user)
def erp_role_edit(request, pk):
    role = get_object_or_404(Role, pk=pk)
    if request.method == 'POST':
        role.name = request.POST.get('name', '')
        role.description = request.POST.get('description', '')
        role.save()
        # Update permissions
        for section, _ in RolePermission.SECTIONS:
            perm, _ = RolePermission.objects.get_or_create(role=role, section=section)
            perm.can_view = request.POST.get(f'perm_{section}_view') == 'on'
            perm.can_create = request.POST.get(f'perm_{section}_create') == 'on'
            perm.can_edit = request.POST.get(f'perm_{section}_edit') == 'on'
            perm.can_delete = request.POST.get(f'perm_{section}_delete') == 'on'
            perm.save()
        messages.success(request, f'Role {role.name} updated.')
        return redirect('erp:role_list')
    perms = {p.section: p for p in role.permissions.all()}
    return render(request, 'portal/role_form.html', {
        'role': role, 'perms': perms, 'sections': RolePermission.SECTIONS, 'edit': True,
    })


@erp_section_required('rfq')
def erp_rfq_list(request):
    rfqs = RFQ.objects.all().select_related('category', 'created_by')
    status = request.GET.get('status')
    if status:
        rfqs = rfqs.filter(status=status)
    return render(request, 'portal/rfq_list.html', {'rfqs': rfqs})


@erp_login_required
def erp_rfq_create(request):
    categories = RFQCategory.objects.filter(is_active=True)
    events = Event.objects.all()
    if request.method == 'POST':
        from decimal import Decimal
        closing_date_str = request.POST.get('closing_date', '')
        closing_date = timezone.datetime.strptime(closing_date_str, '%Y-%m-%dT%H:%M') if closing_date_str else timezone.now()
        budget = request.POST.get('estimated_budget', '').strip()
        rfq = RFQ.objects.create(
            event_id=request.POST.get('event_id') or None,
            category_id=request.POST.get('category_id') or None,
            title=request.POST.get('title', ''),
            description=request.POST.get('description', ''),
            deliverables=request.POST.get('deliverables', ''),
            terms_and_conditions=request.POST.get('terms_and_conditions', ''),
            priority=request.POST.get('priority', 'normal'),
            status='draft',
            closing_date=closing_date,
            estimated_budget=Decimal(budget) if budget else None,
            contact_person=request.POST.get('contact_person', ''),
            contact_email=request.POST.get('contact_email', ''),
            contact_phone=request.POST.get('contact_phone', ''),
            site_visit_required=request.POST.get('site_visit_required') == 'on',
            documents=request.FILES.get('documents'),
            created_by=request.user,
        )
        messages.success(request, f'RFQ {rfq.rfq_number} created. Review and publish when ready.')
        return redirect('erp:rfq_detail', pk=rfq.pk)
    return render(request, 'portal/rfq_form.html', {
        'categories': categories, 'events': events, 'edit': False,
    })


@erp_section_required('rfq')
def erp_rfq_detail(request, pk):
    rfq = get_object_or_404(RFQ.objects.select_related('category', 'created_by', 'event'), pk=pk)
    quotations = rfq.quotations.all().select_related('provider').prefetch_related('documents')
    return render(request, 'portal/rfq_detail.html', {
        'rfq': rfq, 'quotations': quotations,
    })


@erp_login_required
def erp_rfq_edit(request, pk):
    rfq = get_object_or_404(RFQ, pk=pk)
    categories = RFQCategory.objects.filter(is_active=True)
    events = Event.objects.all()
    if request.method == 'POST':
        from decimal import Decimal
        rfq.event_id = request.POST.get('event_id') or None
        rfq.category_id = request.POST.get('category_id') or None
        rfq.title = request.POST.get('title', '')
        rfq.description = request.POST.get('description', '')
        rfq.deliverables = request.POST.get('deliverables', '')
        rfq.terms_and_conditions = request.POST.get('terms_and_conditions', '')
        rfq.priority = request.POST.get('priority', 'normal')
        closing_date_str = request.POST.get('closing_date', '')
        if closing_date_str:
            rfq.closing_date = timezone.datetime.strptime(closing_date_str, '%Y-%m-%dT%H:%M')
        budget = request.POST.get('estimated_budget', '').strip()
        rfq.estimated_budget = Decimal(budget) if budget else None
        rfq.contact_person = request.POST.get('contact_person', '')
        rfq.contact_email = request.POST.get('contact_email', '')
        rfq.contact_phone = request.POST.get('contact_phone', '')
        rfq.site_visit_required = request.POST.get('site_visit_required') == 'on'
        if request.FILES.get('documents'):
            rfq.documents = request.FILES['documents']
        rfq.save()
        messages.success(request, 'RFQ updated.')
        return redirect('erp:rfq_detail', pk=rfq.pk)
    return render(request, 'portal/rfq_form.html', {
        'rfq': rfq, 'categories': categories, 'events': events, 'edit': True,
    })


@erp_login_required
def erp_rfq_publish(request, pk):
    rfq = get_object_or_404(RFQ, pk=pk)
    if rfq.status == 'draft':
        rfq.status = 'open'
        rfq.issue_date = timezone.now().date()
        rfq.published_at = timezone.now()
        rfq.save()
        from notifications.utils import send_rfq_published
        send_rfq_published(rfq)
        messages.success(request, f'RFQ {rfq.rfq_number} published. All providers have been notified.')
    return redirect('erp:rfq_detail', pk=rfq.pk)


@erp_login_required
def erp_rfq_close(request, pk):
    rfq = get_object_or_404(RFQ, pk=pk)
    if rfq.status == 'open':
        rfq.status = 'closed'
        rfq.save()
        messages.success(request, f'RFQ {rfq.rfq_number} closed. No further submissions accepted.')
    return redirect('erp:rfq_detail', pk=rfq.pk)


@erp_section_required('rfq')
def erp_quotation_detail(request, pk):
    quotation = get_object_or_404(
        Quotation.objects.select_related('rfq', 'provider').prefetch_related('documents'),
        pk=pk,
    )
    approvals = quotation.approvals.all().select_related('approved_by')
    return render(request, 'portal/quotation_detail.html', {
        'quotation': quotation, 'approvals': approvals,
    })


@erp_login_required
def erp_quotation_shortlist(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk)
    quotation.status = 'shortlisted'
    quotation.internal_notes = request.POST.get('internal_notes', '')
    quotation.save()
    name = quotation.provider.company_name if quotation.provider else quotation.submitter_company_name
    messages.success(request, f'{name} shortlisted.')
    return redirect('erp:rfq_detail', pk=quotation.rfq.pk)


@erp_login_required
def erp_quotation_reject(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk)
    quotation.status = 'rejected'
    quotation.save()
    from notifications.utils import send_quotation_rejected
    send_quotation_rejected(quotation)
    name = quotation.provider.company_name if quotation.provider else quotation.submitter_company_name
    messages.info(request, f'{name} has been notified of rejection.')
    return redirect('erp:rfq_detail', pk=quotation.rfq.pk)


@erp_login_required
def erp_quotation_approve_first(request, pk):
    """First director approves - marks as pending second approval."""
    quotation = get_object_or_404(Quotation, pk=pk)
    if quotation.status not in ('shortlisted', 'submitted'):
        messages.error(request, 'Quotation must be shortlisted first.')
        return redirect('erp:quotation_detail', pk=pk)
    existing = QuotationApproval.objects.filter(quotation=quotation, approval_order=1).exists()
    if existing:
        messages.warning(request, 'First approval already recorded.')
        return redirect('erp:quotation_detail', pk=pk)
    QuotationApproval.objects.create(
        quotation=quotation,
        approved_by=request.user,
        approval_order=1,
        comments=request.POST.get('comments', ''),
    )
    quotation.status = 'approved_by_first'
    quotation.save()
    # Notify remaining directors
    from notifications.utils import get_director_emails, send_html_email
    remaining = [e for e in get_director_emails() if e != request.user.email]
    if remaining:
        context = {
            'quotation': quotation,
            'rfq': quotation.rfq,
            'approved_by': request.user,
            'site_name': settings.SITE_NAME,
            'site_url': settings.SITE_URL,
        }
        send_html_email(
            f'First Approval Received - {quotation.quotation_number} - {quotation.provider.company_name}',
            'emails/quotation_first_approval.html', context, remaining,
        )
    messages.success(request, f'First approval recorded (1/2). Awaiting second director approval.')
    return redirect('erp:quotation_detail', pk=pk)


@erp_login_required
def erp_quotation_approve_second(request, pk):
    """Second director approves - quotation is accepted."""
    quotation = get_object_or_404(Quotation, pk=pk)
    if quotation.status != 'approved_by_first':
        messages.error(request, 'First approval required before second approval.')
        return redirect('erp:quotation_detail', pk=pk)
    existing = QuotationApproval.objects.filter(quotation=quotation, approval_order=2).exists()
    if existing:
        messages.warning(request, 'Second approval already recorded.')
        return redirect('erp:quotation_detail', pk=pk)
    QuotationApproval.objects.create(
        quotation=quotation,
        approved_by=request.user,
        approval_order=2,
        comments=request.POST.get('comments', ''),
    )
    quotation.status = 'acceptable'
    quotation.save()
    # Mark RFQ as awarded
    rfq = quotation.rfq
    rfq.status = 'awarded'
    rfq.save()

    # Auto-register anonymous submitter as a ServiceProvider, if not already one
    provider_password = None
    provider = quotation.provider
    if not provider:
        from django.contrib.auth.hashers import make_password
        from providers.models import ServiceProvider
        # Default password = contact person name (lowercase, no spaces)
        contact_name = (quotation.submitter_contact_person or 'provider').strip().lower().replace(' ', '_')
        provider_password = contact_name
        provider = ServiceProvider.objects.create(
            email=quotation.submitter_email or f'{contact_name}@alansaar.org.za',
            password=make_password(provider_password),
            company_name=quotation.submitter_company_name or 'Unknown Company',
            company_type=quotation.submitter_company_type or 'other',
            registration_number=quotation.submitter_registration_number or '',
            vat_number=quotation.submitter_vat_number or '',
            phone=quotation.submitter_phone or '',
            contact_person=quotation.submitter_contact_person or '',
            is_verified=True,
            is_active=True,
            must_change_password=True,
        )
        quotation.provider = provider
        quotation.save()
    else:
        # Existing provider: force password change on next login
        provider.must_change_password = True
        provider.save()

    # Notify provider of acceptance (pending site meeting)
    from notifications.utils import send_quotation_accepted
    send_quotation_accepted(quotation, provider_password=provider_password)
    name = provider.company_name
    extra = f' Provider account created. Default password sent to {provider.email}.' if provider_password else ''
    messages.success(
        request,
        f'Quotation ACCEPTED PENDING APPROVAL (2/2). {name} has been notified.{extra} '
        f'A site meeting must be scheduled before final approval.'
    )
    return redirect('erp:quotation_detail', pk=pk)


@erp_login_required
def erp_quotation_schedule_meeting(request, pk):
    """Schedule a site meeting for an accepted-pending-approval quotation."""
    quotation = get_object_or_404(Quotation, pk=pk)
    if quotation.status != 'acceptable':
        messages.error(request, 'Quotation must be in "Accepted Pending Approval" status.')
        return redirect('erp:quotation_detail', pk=pk)
    if request.method == 'POST':
        meeting_date_str = request.POST.get('meeting_date', '').strip()
        if not meeting_date_str:
            messages.error(request, 'Please provide a meeting date and time.')
            return redirect('erp:quotation_detail', pk=pk)
        from django.utils.dateparse import parse_datetime
        meeting_date = parse_datetime(meeting_date_str)
        if not meeting_date:
            messages.error(request, 'Invalid date/time format.')
            return redirect('erp:quotation_detail', pk=pk)
        quotation.site_meeting_date = meeting_date
        quotation.save()
        from notifications.utils import send_quotation_site_meeting
        send_quotation_site_meeting(quotation, meeting_date)
        messages.success(request, f'Site meeting scheduled for {meeting_date.strftime("%d %b %Y at %H:%M")}. Provider notified.')
    return redirect('erp:quotation_detail', pk=pk)


@erp_login_required
def erp_quotation_approve_after_meeting(request, pk):
    """Final approval after site meeting — creates Expense + accounting entry."""
    quotation = get_object_or_404(Quotation, pk=pk)
    if quotation.status not in ('acceptable', 'accepted'):
        messages.error(request, 'Quotation must be in "Accepted Pending Approval" status.')
        return redirect('erp:quotation_detail', pk=pk)
    provider = quotation.provider
    if not provider:
        messages.error(request, 'No provider linked to this quotation.')
        return redirect('erp:quotation_detail', pk=pk)
    quotation.status = 'accepted'
    quotation.save()
    from providers.models import Expense
    existing_expense = Expense.objects.filter(provider=provider, description__contains=quotation.quotation_number).first()
    if not existing_expense:
        expense = Expense.objects.create(
            provider=provider,
            description=f'{quotation.rfq.rfq_number} - {quotation.rfq.title[:80]} - {quotation.quotation_number}',
            category='other',
            amount_excl=quotation.total_amount_excl,
            vat_amount=quotation.vat_amount,
            amount_incl=quotation.total_amount_incl,
            balance_due=quotation.total_amount_incl,
            expense_date=timezone.now().date(),
            due_date=timezone.now().date() + timezone.timedelta(days=30),
            notes=f'Final approval after site meeting. Quotation: {quotation.quotation_number}',
            created_by=request.user,
        )
    else:
        expense = existing_expense
    try:
        from accounting.auto_post import auto_post_accepted_quotation
        auto_post_accepted_quotation(quotation, expense, created_by=request.user)
    except Exception:
        pass
    try:
        from notifications.utils import send_quotation_fully_approved
        send_quotation_fully_approved(quotation)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception(f'Email failed for {quotation.quotation_number}: {e}')
    messages.success(
        request,
        f'Quotation FULLY APPROVED after site meeting. '
        f'Expense record created. Accounting entry posted. '
        f'{provider.company_name} now has a liability balance.'
    )
    return redirect('erp:quotation_detail', pk=pk)
