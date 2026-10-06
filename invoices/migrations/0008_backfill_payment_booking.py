from django.db import migrations


def backfill_payment_booking(apps, schema_editor):
    Payment = apps.get_model('invoices', 'Payment')
    for p in Payment.objects.filter(booking__isnull=True).select_related('invoice'):
        ref = (p.reference_number or '').lower()
        if not ref:
            continue
        candidate = None
        # try to match a stall name mentioned in the reference within this invoice's event
        for line in p.invoice.invoice_lines.select_related('booking', 'booking__stall').all():
            stall = line.booking.stall if line.booking else None
            if stall and stall.name and stall.name.lower() in ref:
                candidate = line.booking
                break
        if candidate is None and p.invoice.event_id:
            from events.models import Stall
            for stall in Stall.objects.filter(event_id=p.invoice.event_id):
                if stall.name and stall.name.lower() in ref:
                    # attach to the exhibitor's booking for that stall if any
                    from bookings.models import Booking
                    b = Booking.objects.filter(stall=stall, exhibitor=p.invoice.exhibitor).order_by('-id').first()
                    if b is not None:
                        candidate = b
                    break
        if candidate is not None:
            p.booking = candidate
            p.save(update_fields=['booking'])


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0007_refund'),
    ]

    operations = [
        migrations.RunPython(backfill_payment_booking, migrations.RunPython.noop),
    ]
