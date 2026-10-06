from django.db import migrations


def fix_eft_methods(apps, schema_editor):
    Payment = apps.get_model('invoices', 'Payment')
    for p in Payment.objects.all():
        n = (p.notes or '').lower()
        if 'eft' in n and p.payment_method != 'eft':
            p.payment_method = 'eft'
            p.save(update_fields=['payment_method'])


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0011_recompute_discounts_grace'),
    ]

    operations = [
        migrations.RunPython(fix_eft_methods, migrations.RunPython.noop),
    ]
