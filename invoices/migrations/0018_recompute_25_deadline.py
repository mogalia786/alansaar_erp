from django.db import migrations
from decimal import Decimal


def recompute(apps, schema_editor):
    from invoices.models import Invoice
    from invoices.views import evaluate_invoice_discounts
    for inv in Invoice.objects.all():
        evaluate_invoice_discounts(inv)
        incl = Decimal('0')
        for line in inv.invoice_lines.select_related('booking').all():
            b = line.booking
            if b is None:
                continue
            stall_price = Decimal(b.stall_price or 0)
            elec = Decimal(b.electricity_deposit or 0) if b.requires_power else Decimal('0')
            i = stall_price + elec + Decimal(b.accessories_total or 0) - Decimal(b.early_payment_discount or 0)
            line.amount_incl = i
            line.amount_excl = i
            line.vat_amount = Decimal('0')
            line.save()
            incl += i
        inv.amount_excl = incl
        inv.vat_amount = Decimal('0')
        inv.amount_incl = incl
        inv.amount_paid = sum((p.amount for p in inv.payments.filter(status='verified')), Decimal('0'))
        inv.balance_due = inv.amount_incl - inv.amount_paid
        inv.save()


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0017_recompute_stallprice_95'),
    ]

    operations = [
        migrations.RunPython(recompute, migrations.RunPython.noop),
    ]
