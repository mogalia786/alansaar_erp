from decimal import Decimal
from django.db import transaction
from django.utils import timezone


@transaction.atomic
def execute_stall_transfer(transfer_request, reviewed_by=None, review_notes=''):
    """Approve a stall transfer request.

    - Old booking is cancelled; its stall becomes available.
    - New booking is created on the requested stall with the exhibitor's
      requirements copied over; stall becomes reserved.
    - The consolidated invoice line is re-pointed at the new booking and
      repriced; verified payments stay on the invoice, so they automatically
      apply to the new stand. Any overpayment remains as credit.
    """
    from bookings.models import Booking, BookingAccessory
    from events.models import Stall
    from invoices.views import refresh_invoice, ensure_booking_invoice
    from invoices.models import LedgerEntry, Payment
    import uuid

    old_booking = transfer_request.booking
    new_stall = transfer_request.requested_stall

    if old_booking.status in ('cancelled', 'rejected', 'completed'):
        raise ValueError('Original booking can no longer be transferred.')
    if new_stall.status != 'available':
        raise ValueError(f'Stall {new_stall.name} is no longer available.')
    if new_stall.event_id != old_booking.event_id:
        raise ValueError('New stall must be in the same event.')

    event = old_booking.event
    old_stall = old_booking.stall
    ref = f"BK-{uuid.uuid4().hex[:8].upper()}"

    old_status = old_booking.status
    # 1. Cancel old booking, free its stall
    old_booking.status = 'cancelled'
    old_booking.payment_status = 'unpaid'
    old_booking.amount_paid = Decimal('0')
    old_booking.balance_due = Decimal('0')
    old_booking.admin_notes = (old_booking.admin_notes or '') + f"\n[Transferred to stall {new_stall.name} via request #{transfer_request.id} on {timezone.now():%Y-%m-%d}]"
    old_booking.save()
    if old_stall:
        old_stall.status = 'available'
        old_stall.save(update_fields=['status'])

    # 2. Create replacement booking copying exhibitor requirements
    elec_dep = event.electricity_deposit if old_booking.requires_power else Decimal('0')
    from bookings.pricing import booking_totals
    subtotal, vat = booking_totals(new_stall.total_price, elec_dep, old_booking.accessories_total, 0)
    new_booking = Booking.objects.create(
        booking_reference=ref,
        event=event,
        exhibitor=old_booking.exhibitor,
        stall=new_stall,
        status='approved',
        stall_price=new_stall.total_price,
        accessories_total=old_booking.accessories_total,
        electricity_deposit=elec_dep,
        subtotal=subtotal,
        vat_amount=vat,
        total_amount=subtotal,
        balance_due=subtotal,
        fascia_name=old_booking.fascia_name,
        terms_accepted=old_booking.terms_accepted,
        requires_power=old_booking.requires_power,
        power_amps=old_booking.power_amps,
        requires_water=old_booking.requires_water,
        require_stand_build=old_booking.require_stand_build,
        require_remove_side_walls=old_booking.require_remove_side_walls,
        side_wall_removal=old_booking.side_wall_removal,
        require_floor_mat=old_booking.require_floor_mat,
        require_carpet=old_booking.require_carpet,
        require_extra_plugs=old_booking.require_extra_plugs,
        require_extra_lights=old_booking.require_extra_lights,
        require_additional_power_amps=old_booking.require_additional_power_amps,
        stand_build_instructions=old_booking.stand_build_instructions,
        exhibitor_requirements=old_booking.exhibitor_requirements,
        special_requirements=old_booking.special_requirements,
        products_description=old_booking.products_description,
        admin_notes=f"Transferred from {old_booking.booking_reference} (stall {old_stall.name if old_stall else '-'})",
        approved_date=timezone.now(),
    )
    # copy accessories
    for ba in old_booking.accessories.all():
        BookingAccessory.objects.create(booking=new_booking, accessory=ba.accessory, quantity=ba.quantity, price=ba.price)

    new_stall.status = 'reserved'
    new_stall.save(update_fields=['status'])

    # 3. Re-point the invoice line to the new booking and reprice
    line = getattr(old_booking, 'invoice_line', None)
    old_booking_invoices = list(old_booking.invoices.all())
    if line is not None:
        inv = line.invoice
        line.booking = new_booking
        line.save()
        from invoices.views import _set_line
        _set_line(inv, new_booking)
        inv.booking = new_booking
        inv.save(update_fields=['booking'])
    else:
        inv = None
        if old_booking_invoices:
            inv = old_booking_invoices[0]
        if inv is not None:
            from invoices.views import _set_line
            _set_line(inv, new_booking)
            inv.booking = new_booking
            inv.save(update_fields=['booking'])
        else:
            inv, _ = ensure_booking_invoice(new_booking)

    # 4. Move payment references to the new booking
    Payment.objects.filter(booking=old_booking).update(booking=new_booking)

    # 5. Recompute invoice + booking payment allocation
    refresh_invoice(inv)

    # Delink old booking from the invoice line relation (keep history)
    # old_booking keeps its cancelled status and financial zeros.

    # 6. Ledger note
    LedgerEntry.objects.create(
        exhibitor=new_booking.exhibitor, booking=new_booking,
        entry_type='debit',
        description=f'Stand transfer from {old_booking.booking_reference} to {new_booking.booking_reference}',
        reference=inv.invoice_number,
        debit=Decimal('0'), credit=Decimal('0'), balance=inv.balance_due,
        entry_date=timezone.localdate(),
    )

    # 7. Mark request approved
    transfer_request.status = 'approved'
    transfer_request.reviewed_by = reviewed_by
    transfer_request.reviewed_at = timezone.now()
    transfer_request.review_notes = review_notes
    transfer_request.new_booking = new_booking
    transfer_request.save()

    # Notify stand builder of the new/updated build requirements
    try:
        from notifications.utils import send_stand_builder_notification
        send_stand_builder_notification(new_booking, change_type='booking')
    except Exception:
        pass

    return new_booking
