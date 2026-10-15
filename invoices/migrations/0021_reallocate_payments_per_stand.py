from django.db import migrations


def reallocate(apps, schema_editor):
    """Re-run invoice refresh so every stand's paid/balance reflects the payment
    the exhibitor actually made for it.

    Prior to this fix the whole invoice total was consumed purely in line order,
    so a payment tagged to one stand could be stamped onto a different stand.
    refresh_invoice() now honours each payment's stand tag, so replaying it here
    corrects the historical per-stand allocations.
    """
    from invoices.models import Invoice
    from invoices.views import refresh_invoice
    for inv in Invoice.objects.all():
        try:
            refresh_invoice(inv)
        except Exception:
            # Never block a deploy on a single problematic invoice; the invoice
            # will be recomputed next time it is opened in the ERP.
            pass


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0020_invoice_discount_amount_invoice_discount_approved_by_and_more'),
    ]

    operations = [
        migrations.RunPython(reallocate, migrations.RunPython.noop),
    ]
