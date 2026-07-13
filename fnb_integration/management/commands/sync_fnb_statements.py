from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from fnb_integration.models import FNBAccount, FNBTransaction
from fnb_integration.services import FNBStatementService


class Command(BaseCommand):
    help = "Fetch FNB bank statements for all active debtor accounts"

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=30, help='Number of days back to fetch')
        parser.add_argument('--account', type=str, default='', help='Specific account number')

    def handle(self, *args, **options):
        days = options['days']
        service = FNBStatementService()
        to_date = timezone.now().strftime("%Y-%m-%d")
        from_date = (timezone.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        accounts = FNBAccount.objects.filter(is_active=True, account_type='debtor')
        if options['account']:
            accounts = accounts.filter(account_number=options['account'])

        if not accounts.exists():
            self.stdout.write(self.style.WARNING("No active debtor accounts found. Use --account or seed data first."))
            return

        total_imported = 0
        for account in accounts:
            self.stdout.write(f"Fetching {account.account_number} up to {to_date} (lookback: {days} days)...")
            try:
                entries = service.fetch_statement_range(account.account_number, to_date, lookback_months=max(1, days // 30))
                transactions = FNBStatementService.parse_entries(entries)
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  Error: {e}"))
                continue

            imported = 0
            for txn in transactions:
                _, created = FNBTransaction.objects.get_or_create(
                    account=account,
                    transaction_date=txn["transaction_date"],
                    description=txn["description"],
                    debit_amount=txn["debit_amount"],
                    credit_amount=txn["credit_amount"],
                    defaults={
                        "reference": txn["reference"],
                        "balance": txn["balance"],
                        "transaction_type": txn["transaction_type"],
                    },
                )
                if created:
                    imported += 1

            self.stdout.write(self.style.SUCCESS(f"  Imported {imported} new transactions (total on record: {account.transactions.count()})"))
            total_imported += imported

        self.stdout.write(self.style.SUCCESS(f"Done. Total new transactions imported: {total_imported}"))
