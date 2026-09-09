from decimal import Decimal
from django.db import migrations
from django.utils import timezone


ACCOUNTS = [
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
    ('4300', 'Daily Gate Takings', 'income'),
    ('4600', 'Discount Income', 'income'),
    ('5000', 'Venue Hire', 'expense'),
    ('5100', 'Marketing & Advertising', 'expense'),
    ('5200', 'Staff Salaries', 'expense'),
    ('5300', 'Utilities', 'expense'),
    ('5400', 'Equipment Rental', 'expense'),
    ('5500', 'Insurance', 'expense'),
    ('5600', 'Bank Charges', 'expense'),
    ('5700', 'Administrative Expenses', 'expense'),
]


def seed_accounts(apps, schema_editor):
    Account = apps.get_model('accounting', 'Account')
    for code, name, atype in ACCOUNTS:
        Account.objects.get_or_create(
            code=code,
            defaults={'name': name, 'type': atype, 'is_active': True},
        )


def backfill_journal_entries(apps, schema_editor):
    """Non-destructively post journal entries for existing transactions that
    were silently skipped because the chart of accounts was missing.

    Only creates entries that do not already exist (description-based dedup).
    Never deletes or rewrites anything.
    """
    Account = apps.get_model('accounting', 'Account')
    JournalEntry = apps.get_model('accounting', 'JournalEntry')
    JournalLine = apps.get_model('accounting', 'JournalLine')
    Invoice = apps.get_model('invoices', 'Invoice')
    Payment = apps.get_model('invoices', 'Payment')
    GateTaking = apps.get_model('accounting', 'GateTaking')

    acc = {}
    for code in ['1000', '1100', '2000', '2100', '4000', '4600', '5000']:
        acc[code] = Account.objects.filter(code=code).first()

    if not all([acc['1000'], acc['1100'], acc['4000'], acc['2100']]):
        return

    counter = 0

    def create_je(date, description):
        nonlocal counter
        counter += 1
        entry_number = f"BKFL-{date.strftime('%Y%m%d')}-{counter:04d}"
        je = JournalEntry.objects.create(
            entry_number=entry_number,
            date=date,
            description=description,
            is_posted=True,
        )
        return je

    def add_line(je, code, description, debit, credit):
        JournalLine.objects.create(
            journal_entry=je, account=acc[code],
            description=description,
            debit=Decimal(str(debit)), credit=Decimal(str(credit)),
        )

    # 1. Invoices
    for inv in Invoice.objects.filter(amount_incl__gt=0).select_related('booking', 'exhibitor').all():
        if JournalEntry.objects.filter(description__startswith=f"Invoice {inv.invoice_number} ").exists():
            continue
        ref = inv.booking.booking_reference if inv.booking else (
            inv.invoice_lines.first().booking.booking_reference if inv.invoice_lines.exists() else inv.invoice_number
        )
        je = create_je(inv.issue_date, f"Invoice {inv.invoice_number} - {inv.exhibitor.company_name}")
        add_line(je, '1100', f"Stall rental - {ref}", inv.amount_incl, 0)
        add_line(je, '4000', "Stall rental income", 0, inv.amount_excl)
        if inv.vat_amount > 0:
            add_line(je, '2100', "VAT on stall rental", 0, inv.vat_amount)

    # 2. Verified payments
    for pay in Payment.objects.filter(status='verified').select_related('invoice').all():
        inv = pay.invoice
        if inv is None:
            continue
        marker = pay.receipt_number or pay.reference_number or str(pay.pk)
        if JournalEntry.objects.filter(description__contains=marker).exists():
            continue
        date = pay.verified_at.date() if pay.verified_at else pay.payment_date.date()
        je = create_je(date, f"Payment {marker} - {inv.invoice_number}")
        add_line(je, '1000', f"Payment received - {inv.invoice_number}", pay.amount, 0)
        add_line(je, '1100', f"Settle {inv.invoice_number}", 0, pay.amount)

    # 3. Approved discounts
    DiscountRequest = apps.get_model('bookings', 'DiscountRequest')
    for dr in DiscountRequest.objects.filter(status='approved').select_related('booking').all():
        bk = dr.booking
        if bk is None:
            continue
        if JournalEntry.objects.filter(description__startswith=f"Discount approved - {bk.booking_reference}").exists():
            continue
        je = create_je(timezone.now().date(), f"Discount approved - {bk.booking_reference} - R{dr.discount_amount}")
        add_line(je, '4600', f"Discount for {bk.booking_reference}", dr.discount_amount, 0)
        add_line(je, '4000', f"Less: Discount on {bk.booking_reference}", 0, dr.discount_amount)

    # 4. Expenses
    Expense = apps.get_model('providers', 'Expense')
    for exp in Expense.objects.select_related('provider').all():
        if JournalEntry.objects.filter(description__startswith=f"Expense - {exp.description[:50]}").exists():
            continue
        je = create_je(exp.expense_date or timezone.now().date(), f"Expense - {exp.description[:50]}")
        add_line(je, '5000', exp.description[:100], exp.amount_excl, 0)
        if exp.vat_amount > 0:
            add_line(je, '2100', f"VAT on expense", exp.vat_amount, 0)
        provider_name = exp.provider.company_name if exp.provider else 'Unknown'
        add_line(je, '2000', f"Payable - {provider_name}", 0, exp.amount_incl)

    # 5. Gate takings
    for gt in GateTaking.objects.filter(journal_entry__isnull=True).all():
        je = create_je(gt.date, f"Daily Gate Takings - {gt.date}")
        add_line(je, '1000', f"Daily gate cash/card deposit - {gt.date}", gt.cash_amount + gt.card_amount, 0)
        add_line(je, '4300', "Gate takings income", 0, gt.cash_amount + gt.card_amount)
        gt.journal_entry = je
        gt.save(update_fields=['journal_entry'])


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0003_seed_gate_takings_account'),
        ('invoices', '0006_invoice_event_alter_invoice_booking_and_more'),
        ('bookings', '0004_discountrequest_rejected_at_and_more'),
        ('providers', '0005_quotation_site_meeting_date_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_accounts, migrations.RunPython.noop),
        migrations.RunPython(backfill_journal_entries, migrations.RunPython.noop),
    ]