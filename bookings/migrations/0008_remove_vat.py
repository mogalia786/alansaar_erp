from django.db import migrations
from decimal import Decimal


def zero_vat(apps, schema_editor):
    Event = apps.get_model('events', 'Event')
    Booking = apps.get_model('bookings', 'Booking')
    Invoice = apps.get_model('invoices', 'Invoice')
    InvoiceLine = apps.get_model('invoices', 'InvoiceLine')
    Event.objects.all().update(vat_rate=0)
    Booking.objects.all().update(vat_amount=Decimal('0'))
    Invoice.objects.all().update(vat_amount=Decimal('0'))
    InvoiceLine.objects.all().update(vat_amount=Decimal('0'))


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0011_alter_event_vat_rate'),
        ('bookings', '0007_stalltransferrequest'),
        ('invoices', '0006_invoice_event_alter_invoice_booking_and_more'),
    ]

    operations = [
        migrations.RunPython(zero_vat, migrations.RunPython.noop),
    ]
