from django.core.management.base import BaseCommand
from django.core.management import call_command


class Command(BaseCommand):
    help = 'Load local data fixture into production'

    def handle(self, *args, **options):
        self.stdout.write('Loading local_data fixture...')
        call_command('loaddata', 'local_data', verbosity=2)
        self.stdout.write(self.style.SUCCESS('Done.'))
