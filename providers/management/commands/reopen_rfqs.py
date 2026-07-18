from django.core.management.base import BaseCommand
from providers.models import RFQ


class Command(BaseCommand):
    help = 'Re-open RFQs that were closed prematurely (closing date still in the future)'

    def handle(self, *args, **options):
        from django.utils import timezone
        fixed = 0
        for rfq in RFQ.objects.filter(status='closed'):
            if rfq.closing_date and rfq.closing_date > timezone.now():
                rfq.status = 'open'
                rfq.save()
                self.stdout.write(f'  Re-opened {rfq.rfq_number} - {rfq.title} (closes {rfq.closing_date})')
                fixed += 1
        self.stdout.write(self.style.SUCCESS(f'Done. Re-opened {fixed} RFQs.'))
