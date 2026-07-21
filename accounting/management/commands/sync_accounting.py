from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from decimal import Decimal
from accounting.models import Account, JournalEntry, JournalLine
from invoices.models import Invoice, Payment, LedgerEntry
from bookings.models import Booking, DiscountRequest
from providers.models import Expense


REQUIRED_ACCOUNTS = [
    ('1000', 'Bank Account', 'asset'),
    ('1100', 'Accounts Receivable', 'asset'),
    ('2000', 'Accounts Payable', 'liability'),
    ('2100', 'VAT Payable', 'liability'),
    ('4000', 'Stall Rental Income', 'income'),
    ('4600', 'Discount Income', 'income'),
    ('5000', 'Venue Hire', 'expense'),
]


class Command(BaseCommand):
    help = 'Wipe all journal entries and rebuild from invoices, payments, discounts, and expenses'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Preview without writing')

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        accounts = {}
        for code, name, atype in REQUIRED_ACCOUNTS:
            acc, _ = Account.objects.get_or_create(code=code, defaults={'name': name, 'type': atype, 'is_active': True})
            accounts[code] = acc
        self.stdout.write(f'Accounts ready: {", ".join(accounts.keys())}')

        acc_bank = accounts['1000']
        acc_ar = accounts['1100']
        acc_ap = accounts['2000']
        acc_vat = accounts['2100']
        acc_income = accounts['4000']
        acc_discount = accounts['4600']
        acc_expense = accounts['5000']

        if dry_run:
            count = JournalEntry.objects.count()
            self.stdout.write(f'Would delete {count} journal entries and rebuild')
        else:
            JournalLine.objects.all().delete()
            JournalEntry.objects.all().delete()
            self.stdout.write(f'Cleared all journal entries')

        transactions = []

        for inv in Invoice.objects.select_related('booking', 'booking__stall', 'exhibitor').all():
            if inv.amount_incl > 0:
                transactions.append(('invoice', inv.issue_date, inv))

        for pay in Payment.objects.select_related('invoice', 'invoice__booking', 'booking', 'booking__stall').filter(status='verified'):
            date = pay.verified_at.date() if pay.verified_at else pay.payment_date.date()
            transactions.append(('payment', date, pay))

        for dr in DiscountRequest.objects.filter(status='approved').select_related('booking', 'booking__stall', 'booking__exhibitor'):
            transactions.append(('discount', timezone.now().date(), dr))

        for exp in Expense.objects.select_related('provider').all():
            transactions.append(('expense', exp.expense_date, exp))

        transactions.sort(key=lambda x: x[1])
        self.stdout.write(f'Found {len(transactions)} transactions to post')

        counter = 0
        with transaction.atomic():
            for tx_type, date, obj in transactions:
                counter += 1
                entry_number = f"SYNC-{date.strftime('%Y%m')}-{counter:04d}"

                if tx_type == 'invoice':
                    je = self._create_je(entry_number, date, f"Invoice {obj.invoice_number} - {obj.exhibitor.company_name}")
                    self._line(je, acc_ar, f"Stall rental - {obj.booking.booking_reference}", obj.amount_incl, 0)
                    self._line(je, acc_income, f"Stall rental income", 0, obj.amount_excl)
                    if obj.vat_amount > 0:
                        self._line(je, acc_vat, f"VAT on {obj.invoice_number}", 0, obj.vat_amount)

                elif tx_type == 'payment':
                    desc = f"Payment {obj.receipt_number or obj.reference_number} - {obj.invoice.invoice_number}"
                    je = self._create_je(entry_number, date, desc)
                    self._line(je, acc_bank, f"Received - {obj.invoice.invoice_number}", obj.amount, 0)
                    self._line(je, acc_ar, f"Settle {obj.invoice.invoice_number}", 0, obj.amount)

                elif tx_type == 'discount':
                    bk = obj.booking
                    je = self._create_je(entry_number, date, f"Discount {obj.discount_percent}% - {bk.booking_reference}")
                    self._line(je, acc_discount, f"Discount for {bk.booking_reference}", obj.discount_amount, 0)
                    self._line(je, acc_income, f"Less discount on {bk.booking_reference}", 0, obj.discount_amount)

                elif tx_type == 'expense':
                    desc = f"Expense - {obj.description[:60]}"
                    je = self._create_je(entry_number, date, desc)
                    self._line(je, acc_expense, f"{obj.description[:100]}", obj.amount_excl, 0)
                    if obj.vat_amount > 0:
                        self._line(je, acc_vat, f"VAT on expense", obj.vat_amount, 0)
                    self._line(je, acc_ap, f"Payable - {obj.provider.company_name if obj.provider else 'Unknown'}", 0, obj.amount_incl)

        self.stdout.write(self.style.SUCCESS(f'Synced {counter} journal entries'))

    def _create_je(self, entry_number, date, description):
        return JournalEntry.objects.create(entry_number=entry_number, date=date, description=description, is_posted=True)

    def _line(self, je, account, description, debit, credit):
        JournalLine.objects.create(journal_entry=je, account=account, description=description, debit=Decimal(str(debit)), credit=Decimal(str(credit)))
