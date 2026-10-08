from django.db import migrations, models
from decimal import Decimal


def cleanup_cancelled_bookings(apps, schema_editor):
    Booking = apps.get_model('bookings', 'Booking')
    Payment = apps.get_model('invoices', 'Payment')
    Refund = apps.get_model('invoices', 'Refund')
    LedgerEntry = apps.get_model('invoices', 'LedgerEntry')
    from invoices.views import refresh_invoice
    for b in Booking.objects.filter(status__in=['cancelled', 'rejected']).select_related('stall'):
        # zero the invoice line
        line = getattr(b, 'invoice_line', None)
        inv = line.invoice if line is not None else b.invoices.first()
        if line is not None:
            line.description = f"CANCELLED - {line.description}" if not line.description.startswith('CANCELLED') else line.description
            line.amount_excl = Decimal('0')
            line.vat_amount = Decimal('0')
            line.amount_incl = Decimal('0')
            line.save()
        if inv is not None:
            refresh_invoice(inv)
        # booking financials cleared
        attributed = Payment.objects.filter(booking=b, status='verified').aggregate(s=models.Sum('amount'))['s'] or Decimal('0')
        paid_to_stand = attributed if attributed > 0 else b.amount_paid
        b.status = b.status
        b.payment_status = 'unpaid'
        b.amount_paid = Decimal('0')
        b.balance_due = Decimal('0')
        b.save()
        # record refund if they paid and not already recorded
        if paid_to_stand > 0 and not Refund.objects.filter(booking=b).exists():
            Refund.objects.create(
                booking=b, amount=paid_to_stand, status='pending',
                reason='Cancelled', notes=f'Paid to stand {b.stall.name if b.stall else "-"} before cancellation',
            )
            LedgerEntry.objects.create(
                exhibitor=b.exhibitor, booking=b, entry_type='credit',
                description=f'Booking cancelled - refund of R{paid_to_stand} due',
                reference=b.booking_reference, debit=0, credit=paid_to_stand,
                balance=0, entry_date=(b.booking_date.date() if b.booking_date else __import__('django.utils.timezone', fromlist=['timezone']).localdate()),
            )
        # release stall if nothing else active
        if b.stall_id:
            has_active = Booking.objects.filter(stall=b.stall_id, status__in=['pending', 'approved', 'confirmed', 'completed']).exists()
            if not has_active:
                b.stall.status = 'available'
                b.stall.save(update_fields=['status'])


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0011_release_cancelled_stalls'),
    ]

    operations = [
        migrations.RunPython(cleanup_cancelled_bookings, migrations.RunPython.noop),
    ]
