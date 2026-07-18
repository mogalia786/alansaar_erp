from django.core.management.base import BaseCommand
from providers.models import Quotation, ServiceProvider


class Command(BaseCommand):
    help = 'Link orphaned quotations to providers by matching email'

    def handle(self, *args, **options):
        providers = {p.email.lower(): p for p in ServiceProvider.objects.filter(is_active=True)}
        fixed = 0
        for q in Quotation.objects.filter(provider__isnull=True):
            email = (q.submitter_email or '').lower().strip()
            if email in providers:
                q.provider = providers[email]
                q.save()
                self.stdout.write(f'  Linked {q.quotation_number} -> {q.provider}')
                fixed += 1
        self.stdout.write(self.style.SUCCESS(f'Done. Fixed {fixed} quotations.'))
