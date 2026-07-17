import json
import os
import tempfile
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.db import transaction, connection

User = get_user_model()

USER_FK_MAP = {
    'bookings.booking': ['exhibitor'],
    'bookings.discountrequest': ['requested_by', 'approved_by_first', 'approved_by_second', 'rejected_by'],
    'invoices.invoice': ['exhibitor'],
    'invoices.payment': ['verified_by'],
    'invoices.receipt': ['exhibitor'],
    'invoices.ledgerentry': ['exhibitor'],
}

TARGET_MODELS = {
    'accounts.role', 'accounts.rolepermission',
    'events.venue', 'events.zone', 'events.event', 'events.accessorytype',
    'events.floorplan', 'events.stall',
    'bookings.booking', 'bookings.bookingaccessory', 'bookings.discountrequest',
    'invoices.invoice', 'invoices.payment', 'invoices.receipt',
    'invoices.ledgerentry', 'invoices.paymentreminder',
}


class Command(BaseCommand):
    help = 'Load local data fixture into production with FK remapping'

    def handle(self, *args, **options):
        self.stdout.write('Reading fixture...')
        with open('fixtures/local_data.json', 'r') as f:
            data = json.load(f)

        local_user_pks = {}
        for item in data:
            if item['model'] == 'accounts.user' and item.get('pk'):
                local_user_pks[item['pk']] = item['fields'].get('username', '')
        self.stdout.write(f'Local users: {local_user_pks}')

        prod_username_to_pk = {u.username: u.id for u in User.objects.all()}
        self.stdout.write(f'Prod users: {prod_username_to_pk}')

        pk_map = {}
        missing = []
        for local_pk, username in local_user_pks.items():
            if username in prod_username_to_pk:
                pk_map[local_pk] = prod_username_to_pk[username]
            else:
                missing.append((local_pk, username))

        if missing:
            self.stdout.write(self.style.WARNING(f'Creating {len(missing)} missing users on production...'))
            for item in data:
                if item['model'] == 'accounts.user' and item.get('pk') in [m[0] for m in missing]:
                    username = item['fields'].get('username', '')
                    fields = dict(item['fields'])
                    fields.pop('user_permissions', None)
                    fields.pop('groups', None)
                    fields.pop('password', None)
                    user_fields = {k: v for k, v in fields.items() if k in [f.name for f in User._meta.get_fields()] and k != 'username'}
                    try:
                        u = User(username=username, **user_fields)
                        u.set_password('changeme123')
                        u.save()
                        pk_map[item['pk']] = u.id
                        prod_username_to_pk[username] = u.id
                        self.stdout.write(self.style.SUCCESS(f'  Created {username} (id={u.id})'))
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f'  Failed to create {username}: {e}'))
        self.stdout.write(f'User PK map: {pk_map}')

        for item in data:
            if item['model'] not in TARGET_MODELS:
                continue
            fields = item['fields']
            for fk_field in USER_FK_MAP.get(item['model'], []):
                if fk_field in fields and fields[fk_field] is not None:
                    old_pk = fields[fk_field]
                    if isinstance(old_pk, int):
                        fields[fk_field] = pk_map.get(old_pk, old_pk)

        filtered = [item for item in data if item['model'] in TARGET_MODELS and item.get('pk')]
        self.stdout.write(f'Filtered to {len(filtered)} records')

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as tmp:
            json.dump(filtered, tmp, ensure_ascii=True, indent=2)
            tmp_path = tmp.name

        self.stdout.write('Loading fixture with loaddata...')
        try:
            call_command('loaddata', tmp_path, verbosity=2, stdout=self.stdout)
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'loaddata raised: {e}'))

        os.unlink(tmp_path)
        self.stdout.write(self.style.SUCCESS('Done.'))
