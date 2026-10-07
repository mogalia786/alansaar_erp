from django.db import migrations


def release_cancelled_stalls(apps, schema_editor):
    Booking = apps.get_model('bookings', 'Booking')
    Stall = apps.get_model('events', 'Stall')
    for b in Booking.objects.filter(status__in=['cancelled', 'rejected']).select_related('stall'):
        if not b.stall_id or not b.stall:
            continue
        has_active = Booking.objects.filter(stall=b.stall, status__in=['pending', 'approved', 'confirmed', 'completed']).exists()
        if not has_active and b.stall.status != 'available':
            b.stall.status = 'available'
            b.stall.save(update_fields=['status'])


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0010_apply_early_payment_discounts'),
        ('events', '0011_alter_event_vat_rate'),
    ]

    operations = [
        migrations.RunPython(release_cancelled_stalls, migrations.RunPython.noop),
    ]
