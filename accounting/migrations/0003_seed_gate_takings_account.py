from django.db import migrations


def seed_gate_takings_account(apps, schema_editor):
    Account = apps.get_model('accounting', 'Account')
    Account.objects.update_or_create(
        code='4300',
        defaults={
            'name': 'Daily Gate Takings',
            'type': 'income',
            'is_active': True,
            'description': 'Cash and card collected at the event gates',
        },
    )


def unseed_gate_takings_account(apps, schema_editor):
    Account = apps.get_model('accounting', 'Account')
    Account.objects.filter(code='4300').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0002_gatetaking'),
    ]

    operations = [
        migrations.RunPython(seed_gate_takings_account, unseed_gate_takings_account),
    ]