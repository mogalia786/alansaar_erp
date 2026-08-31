"""
reset_floor_plan — Clear bookings, invoices, payments, and stalls for an event,
then re-import stall data from stall_export.json.

Usage:
    python manage.py reset_floor_plan --event 1 --import stall_export.json
    python manage.py reset_floor_plan --event 1 --clear-only
    python manage.py reset_floor_plan --event 1 --import stall_export.json --dry-run
"""
import json
from decimal import Decimal
from django.core.management.base import BaseCommand
from events.models import Event, Stall, FloorPlanSection
from bookings.models import Booking
from invoices.models import Invoice, Payment


class Command(BaseCommand):
    help = 'Reset floor plan data: clear bookings/stalls and optionally re-import from JSON'

    def add_arguments(self, parser):
        parser.add_argument('--event', type=int, required=True, help='Event ID')
        parser.add_argument('--import', dest='import_file', type=str, help='Path to stall_export.json')
        parser.add_argument('--clear-only', action='store_true', help='Only clear data, do not import')
        parser.add_argument('--dry-run', action='store_true', help='Show what would be done without doing it')

    def handle(self, *args, **options):
        event_id = options['event']
        event = Event.objects.get(pk=event_id)
        dry_run = options['dry_run']

        self.stdout.write(f'\n{"[DRY RUN] " if dry_run else ""}Resetting floor plan for: {event.name} (id={event_id})\n')

        # 1. Count what will be deleted
        bookings = Booking.objects.filter(event=event)
        invoices = Invoice.objects.filter(event=event)
        payments = Payment.objects.filter(invoice__event=event)
        stalls = Stall.objects.filter(event=event)

        self.stdout.write(f'  Bookings to delete: {bookings.count()}')
        self.stdout.write(f'  Invoices to delete: {invoices.count()}')
        self.stdout.write(f'  Payments to delete: {payments.count()}')
        self.stdout.write(f'  Stalls to delete: {stalls.count()}')

        if dry_run:
            if not options['clear_only'] and options.get('import_file'):
                with open(options['import_file'], 'r') as f:
                    data = json.load(f)
                sections = set(d['section'] for d in data)
                self.stdout.write(f'  Stalls to import: {len(data)} across sections: {", ".join(sections)}')
            self.stdout.write('\n[DRY RUN] No changes made.\n')
            return

        # 2. Clear data
        self.stdout.write('\nDeleting payments...')
        payments.delete()
        self.stdout.write('Deleting invoices...')
        invoices.delete()
        self.stdout.write('Deleting bookings...')
        bookings.delete()
        self.stdout.write('Deleting stalls...')
        stalls.delete()
        self.stdout.write(f'  Cleared {stalls.count()} stalls, {bookings.count()} bookings, {invoices.count()} invoices\n')

        # 3. Import from JSON
        if options.get('import_file'):
            with open(options['import_file'], 'r') as f:
                data = json.load(f)

            sections_map = {}
            for s in FloorPlanSection.objects.filter(event=event):
                sections_map[s.name] = s

            created = 0
            skipped = 0
            for d in data:
                section = sections_map.get(d['section'])
                if not section:
                    self.stdout.write(f'  Skipping {d["name"]}: section "{d["section"]}" not found')
                    skipped += 1
                    continue

                Stall.objects.create(
                    event=event,
                    section=section,
                    name=d['name'],
                    position_x=d['position_x'],
                    position_y=d['position_y'],
                    width=d['width'],
                    height=d['height'],
                    size_sqm=d['size_sqm'],
                    base_price=Decimal(str(d['base_price'])),
                    status=d.get('status', 'available'),
                    rotation=d.get('rotation', 0),
                    has_water=d.get('has_water', False),
                    has_wifi=d.get('has_wifi', False),
                    is_corner=d.get('is_corner', False),
                    is_near_entrance=d.get('is_near_entrance', False),
                    is_accessible=d.get('is_accessible', False),
                )
                created += 1

            self.stdout.write(self.style.SUCCESS(
                f'\nDone! Created {created} stalls, skipped {skipped}\n'
                f'Sections: {", ".join(f"{k}: {v.stalls.count()}" for k, v in sections_map.items())}\n'
            ))
        else:
            self.stdout.write(self.style.SUCCESS('\nDone! All data cleared.\n'))
