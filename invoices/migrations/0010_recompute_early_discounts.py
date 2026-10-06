from django.db import migrations
from decimal import Decimal
import datetime


def recompute_early_discounts(apps, schema_editor):
    Invoice = apps.get_model('invoices', 'Invoice')
    Payment = apps.get_model('invoices', 'Payment')
    for inv in Invoice.objects.all():
        payments = list(Payment.objects.filter(invoice=inv, status='verified').order_by('payment_date'))
        tagged = {}
        untagged = []
        for p in payments:
            if p.booking_id:
                tagged.setdefault(p.booking_id, []).append(p)
            else:
                untagged.append(p)
        for line in inv.invoice_lines.select_related('booking').all():
            b = line.booking
            if b is None:
                continue
            pool = list(tagged.get(b.id, [])) + list(untagged)
            target = Decimal(b.stall_price or 0)
            covered = Decimal('0')
            fully = None
            consumed = []
            for p in sorted(pool, key=lambda x: x.payment_date or datetime.datetime.max):
                covered += p.amount
                if p.booking_id is None:
                    consumed.append(p)
                if covered >= target:
                    fully = p.payment_date.date() if p.payment_date else None
                    break
            for p in consumed:
                if p in untagged:
                    untagged.remove(p)
            discount = Decimal('0')
            tier = ''
            if fully is not None and target > 0:
                if fully <= datetime.date(2026, 9, 30):
                    discount = (target * Decimal('0.05')).quantize(Decimal('0.01')); tier = '5'
                elif fully <= datetime.date(2026, 10, 31):
                    discount = (target * Decimal('0.025')).quantize(Decimal('0.01')); tier = '2.5'
            b.early_payment_discount = discount
            b.early_payment_tier = tier
            b.total_amount = (b.subtotal or Decimal('0')) - discount
            b.balance_due = b.total_amount - (b.amount_paid or Decimal('0'))
            b.save()
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
        ('invoices', '0009_reprice_invoice_lines'),
        ('bookings', '0010_apply_early_payment_discounts'),
    ]

    operations = [
        migrations.RunPython(recompute_early_discounts, migrations.RunPython.noop),
    ]
