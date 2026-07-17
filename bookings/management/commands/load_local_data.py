import json
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.db import connection


class Command(BaseCommand):
    help = 'Load local data fixture into production'

    def handle(self, *args, **options):
        fixture_path = 'fixtures/local_data.json'
        self.stdout.write(f'Loading {fixture_path}...')

        with open(fixture_path, 'r') as f:
            data = json.load(f)

        models_seen = set()
        for item in data:
            models_seen.add(item['model'])

        self.stdout.write(f'Models in fixture: {sorted(models_seen)}')

        for item in data:
            model = item['model']
            pk = item['pk']
            fields = item['fields']
            try:
                call_command('loaddata', fixture_path, verbosity=0)
                self.stdout.write(self.style.SUCCESS('Fixture loaded successfully.'))
                return
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'loaddata failed: {e}'))
                break

        self.stdout.write('Falling back to manual insert with conflict handling...')
        app_label, model_name = models_seen.pop().split('.')
        for item in data:
            model_label = item['model']
            al, mn = model_label.split('.')
            from django.apps import apps
            try:
                Model = apps.get_model(al, mn)
            except LookupError:
                self.stdout.write(self.style.WARNING(f'Model {model_label} not found, skipping'))
                continue

            pk = item['pk']
            fields = item['fields']

            fk_fields = {}
            regular_fields = {}
            for k, v in fields.items():
                if isinstance(v, list):
                    fk_fields[k] = v
                else:
                    regular_fields[k] = v

            try:
                obj = Model.objects.get(pk=pk)
                for k, v in regular_fields.items():
                    setattr(obj, k, v)
                obj.save()
            except Model.DoesNotExist:
                obj = Model(**regular_fields)
                obj.pk = pk
                obj.save()
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'Error saving {model_label} pk={pk}: {e}'))

        self.stdout.write(self.style.SUCCESS('Manual load complete.'))
