from django.core.management.base import BaseCommand
from fnb_integration.models import FNBAccount


class Command(BaseCommand):
    help = "Seed FNB test accounts from the integration guide"

    def handle(self, *args, **options):
        accounts_data = [
            # Al Ansaar's own business accounts (debtor)
            {"account_number": "63001731248", "account_type": "debtor", "account_holder": "Al Ansaar Foundation", "description": "Al Ansaar Main Business Account"},
            {"account_number": "63001723469", "account_type": "debtor", "account_holder": "Al Ansaar Foundation", "description": "Al Ansaar Secondary Account"},
            # Beneficiary accounts (creditors)
            {"account_number": "63001730117", "account_type": "creditor", "account_holder": "Beneficiary One", "description": "Test Beneficiary 1"},
            {"account_number": "63001731222", "account_type": "creditor", "account_holder": "Beneficiary Two", "description": "Test Beneficiary 2"},
        ]
        created = 0
        for data in accounts_data:
            _, is_new = FNBAccount.objects.get_or_create(
                account_number=data["account_number"],
                defaults=data,
            )
            if is_new:
                created += 1
                self.stdout.write(self.style.SUCCESS(f"  Created: {data['account_number']} ({data['account_type']})"))
        self.stdout.write(self.style.SUCCESS(f"Done. {created} new accounts created."))
