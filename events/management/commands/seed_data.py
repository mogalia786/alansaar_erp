from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.core.files import File
from django.utils import timezone
from events.models import Venue, Event, Zone, Stall, FloorPlan, AccessoryType
from accounts.models import Role, RolePermission
from decimal import Decimal
from django.conf import settings

User = get_user_model()


class Command(BaseCommand):
    help = 'Seed the database with test data'

    def handle(self, *args, **options):
        Site.objects.update_or_create(id=1, defaults={
            'domain': '127.0.0.1:8000',
            'name': 'Al Ansaar Event Management',
        })
        self.stdout.write(self.style.SUCCESS('Site record created'))

        admin, _ = User.objects.update_or_create(
            username='admin',
            defaults={
                'email': 'admin@alansaar.org',
                'user_type': 'superadmin',
                'company_name': 'Al Ansaar Foundation',
                'is_staff': True,
                'is_superuser': True,
            }
        )
        admin.set_password('admin123')
        admin.save()
        self.stdout.write(self.style.SUCCESS(f'Admin user: admin / admin123'))

        for name, utype in [('Mr Bux', 'director'), ('Mr Sakoor', 'director')]:
            u, _ = User.objects.update_or_create(
                username=name.lower().replace(' ', '_'),
                defaults={
                    'email': 'alansaar@mogalia.co.za',
                    'user_type': utype,
                    'company_name': f'Al Ansaar Foundation - {name}',
                    'is_staff': True,
                }
            )
            u.set_password('director123')
            u.save()
            self.stdout.write(self.style.SUCCESS(f'Director: {name} / director123'))

        venue, _ = Venue.objects.update_or_create(
            name='Durban Exhibition Centre (DEC)',
            defaults={
                'address': '11 Walnut Road, Durban, 4001',
                'width_meters': 120,
                'length_meters': 80,
            }
        )

        event, _ = Event.objects.update_or_create(
            name='Durban Summer Souk 2026',
            defaults={
                'venue': venue,
                'description': 'The premier shopping festival of Durban featuring local artisans, food vendors, and retail exhibitors.',
                'start_date': '2026-12-01',
                'end_date': '2026-12-31',
                'status': 'published',
                'booking_open': True,
                'is_public': True,
                'max_stalls_per_exhibitor': 3,
            }
        )
        self.stdout.write(self.style.SUCCESS(f'Event: {event.name}'))

        fp_path = settings.BASE_DIR / 'media' / 'floor_plans' / 'dec_floor_plan.svg'
        if not fp_path.exists():
            fp_path = settings.BASE_DIR / 'media' / 'Durban Exhibition Centre Blank Floor Plan with 1x1 Grid Presentation.svg'
        fp, _ = FloorPlan.objects.update_or_create(
            event=event,
            defaults={
                'hall_width_meters': Decimal('21'),
                'hall_height_meters': Decimal('29'),
                'original_width': 2100,
                'original_height': 2970,
                'scale_factor': 20.0,
                'grid_spacing_px': 20,
                'snap_to_grid_px': 20,
            }
        )
        if fp_path.exists():
            with open(fp_path, 'rb') as f:
                fp.image.save('dec_floor_plan.svg', File(f), save=True)
        self.stdout.write(self.style.SUCCESS(f'Floor plan: {"linked" if fp.image else "no image"}'))

        zone_map = {}
        for z_name, z_type, z_color, bookable in [
            ('Hall 1', 'exhibition', '#5B2C6F', True),
            ('Hall 2 West', 'exhibition', '#7B3F95', True),
            ('Hall 2 Central', 'exhibition', '#6C3483', True),
            ('Hall 2 East', 'exhibition', '#8E44AD', True),
            ('Coast of Dreams', 'exhibition', '#00838f', True),
            ('Mystrals', 'exhibition', '#e74c3c', True),
            ('Hall 6A', 'exhibition', '#2980b9', True),
            ('Hall 6B', 'exhibition', '#3498db', True),
            ('Food Court', 'food', '#c2185b', True),
            ('Outdoor Gardens', 'exhibition', '#27ae60', True),
            ('North Plaza', 'entrance', '#7f8c8d', False),
            ('South Plaza', 'entrance', '#7f8c8d', False),
            ('Exhibition Centre', 'exhibition', '#34495e', True),
            ('Parking', 'parking', '#95a5a6', False),
        ]:
            zone, _ = Zone.objects.update_or_create(
                event=event, name=z_name,
                defaults={'zone_type': z_type, 'color': z_color, 'is_bookable': bookable}
            )
            zone_map[z_name] = zone

        Stall.objects.filter(event=event).delete()
        self.stdout.write(self.style.SUCCESS(f'{len(zone_map)} zones created (stalls are placed by staff via floor plan editor)'))

        accessories = [
            ('Electrical Connection (15A)', 'Single phase 15A power point', 350, 'per connection', 'bi-plugin'),
            ('Electrical Connection (30A)', 'Single phase 30A power point', 650, 'per connection', 'bi-plugin'),
            ('Electrical Connection (60A)', 'Three phase 60A power point', 1200, 'per connection', 'bi-plugin'),
            ('Additional Lighting', 'Extra spotlights (per set of 2)', 450, 'per set', 'bi-lightbulb'),
            ('Fascia Board', 'Custom printed fascia board with company name', 850, 'per board', 'bi-signpost'),
            ('Additional Shelving', 'Extra shelves (per shelf)', 250, 'per shelf', 'bi-layers'),
            ('Display Cabinet', 'Lockable glass display cabinet', 1200, 'per unit', 'bi-window'),
            ('Chair (Extra)', 'Additional folding chair', 75, 'per chair', 'bi-chair'),
            ('Table (Extra)', 'Additional trestle table', 350, 'per table', 'bi-table'),
            ('Carpet (Additional)', 'Extra carpet area per m²', 180, 'per m²', 'bi-grid'),
            ('WiFi Access', 'High-speed WiFi for the event duration', 500, 'per connection', 'bi-wifi'),
            ('Water Connection', 'Direct water supply to stall', 800, 'per connection', 'bi-droplet'),
        ]
        for i, (name, desc, price, unit, icon) in enumerate(accessories):
            AccessoryType.objects.update_or_create(
                name=name,
                defaults={
                    'description': desc, 'price': Decimal(str(price)),
                    'unit': unit, 'icon': icon, 'display_order': i, 'is_active': True,
                }
            )
        self.stdout.write(self.style.SUCCESS(f'{AccessoryType.objects.count()} accessory types created'))
        # ── Roles & Permissions (admins configure features via /erp/roles/) ──
        for rname in ('Finance', 'Staff', 'Director', 'Admin'):
            role, created = Role.objects.update_or_create(name=rname, defaults={'description': f'{rname} role'})
            # Create all sections with default view-only (admin enables features in UI)
            for section, _ in RolePermission.SECTIONS:
                RolePermission.objects.update_or_create(
                    role=role, section=section,
                    defaults={'can_view': True, 'can_create': False, 'can_edit': False, 'can_delete': False},
                )
            self.stdout.write(self.style.SUCCESS(f'Role: {rname} ({"created" if created else "updated"})'))
        self.stdout.write(self.style.SUCCESS('Database seeded successfully!'))
