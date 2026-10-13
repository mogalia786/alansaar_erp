from django.db import migrations


def release_stuck_cancelled_stalls(apps, schema_editor):
    """Release stalls left 'reserved'/'confirmed' after their booking was cancelled.

    A cancelled booking's invoice line is zeroed, and `refresh_invoice` used to
    treat a zeroed line as fully paid (0 >= 0), re-confirming the booking and its
    stall while the booking was still 'approved'. The stall therefore stayed
    reserved/confirmed even though the booking was cancelled. This releases any
    such stall that has no remaining active booking.
    """
    Booking = apps.get_model('bookings', 'Booking')
    for b in Booking.objects.filter(status__in=['cancelled', 'rejected']).select_related('stall'):
        if not b.stall_id or not b.stall:
            continue
        has_active = Booking.objects.filter(
            stall=b.stall,
            status__in=['pending', 'approved', 'confirmed', 'completed'],
        ).exists()
        if not has_active and b.stall.status != 'available':
            b.stall.status = 'available'
            b.stall.save(update_fields=['status'])


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0012_refund_cleanup_cancelled'),
    ]

    operations = [
        migrations.RunPython(release_stuck_cancelled_stalls, migrations.RunPython.noop),
    ]
