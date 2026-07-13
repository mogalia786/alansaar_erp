from django.core.management.base import BaseCommand
from accounting.models import Account, JournalEntry, JournalLine
from django.utils import timezone
from decimal import Decimal


class Command(BaseCommand):
    help = 'Seed chart of accounts and demo journal entries'

    def handle(self, *args, **options):
        accounts_data = [
            ('1000', 'Bank Account', 'asset'),
            ('1100', 'Accounts Receivable', 'asset'),
            ('1200', 'Prepaid Expenses', 'asset'),
            ('1300', 'Deposits Paid', 'asset'),
            ('2000', 'Accounts Payable', 'liability'),
            ('2100', 'VAT Payable', 'liability'),
            ('2200', 'Deposits Received', 'liability'),
            ('3000', 'Retained Earnings', 'equity'),
            ('4000', 'Stall Rental Income', 'income'),
            ('4100', 'Accessory Sales', 'income'),
            ('4200', 'Service Fees', 'income'),
            ('5000', 'Venue Hire', 'expense'),
            ('5100', 'Marketing & Advertising', 'expense'),
            ('5200', 'Staff Salaries', 'expense'),
            ('5300', 'Utilities', 'expense'),
            ('5400', 'Equipment Rental', 'expense'),
            ('5500', 'Insurance', 'expense'),
            ('5600', 'Bank Charges', 'expense'),
            ('5700', 'Administrative Expenses', 'expense'),
        ]
        for code, name, atype in accounts_data:
            acc, created = Account.objects.update_or_create(
                code=code, defaults={'name': name, 'type': atype, 'is_active': True}
            )
            if created:
                self.stdout.write(f'  Created: {acc}')

        self.stdout.write(self.style.SUCCESS(f'Chart of accounts: {Account.objects.count()} accounts'))
