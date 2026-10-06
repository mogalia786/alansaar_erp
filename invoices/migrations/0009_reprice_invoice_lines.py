from django.db import migrations
from decimal import Decimal


def reprice_invoice_lines(apps, schema_editor):
    InvoiceLine = apps.get_model('invoices', 'InvoiceLine')
    Invoice = apps.get_model('invoices', 'Invoice')
    for line in InvoiceLine.objects.select_related('booking', 'booking__stall', 'booking__event').all():
        b = line.booking
        if b is None:
            continue
        stall_price = Decimal(b.stall_price or 0)
        elec = Decimal(b.electricity_deposit or 0) if b.requires_power else Decimal('0')
        incl = stall_price + elec + Decimal(b.accessories_total or 0) - Decimal(b.early_payment_discount or 0)
        line.amount_incl = incl
        line.amount_excl = incl
        line.vat_amount = Decimal('0')
        line.save()
    for inv in Invoice.objects.all():
        incl = sum((l.amount_incl for l in inv.invoice_lines.all()), Decimal('0'))
        paid = sum((p.amount for p in inv.payments.filter(status='verified')), Decimal('0'))
        inv.amount_excl = incl
        inv.vat_amount = Decimal('0')
        inv.amount_incl = incl
        inv.amount_paid = paid
        inv.balance_due = incl - paid
        inv.save()


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0008_backfill_payment_booking'),
        ('bookings', '0010_apply_early_payment_discounts'),
    ]

    operations = [
        migrations.RunPython(reprice_invoice_lines, migrations.RunPython.noop),
    ]
