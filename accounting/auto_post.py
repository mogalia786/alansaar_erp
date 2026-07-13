from django.utils import timezone
from decimal import Decimal
from .models import Account, JournalEntry, JournalLine


def auto_post_expense(expense, created_by=None):
    acc_expense = Account.objects.filter(code='5000').first()
    acc_vat = Account.objects.filter(code='2100').first()
    acc_ap = Account.objects.filter(code='2000').first()
    if not all([acc_expense, acc_vat, acc_ap]):
        return
    last_num = JournalEntry.objects.count()
    entry_number = f"EXP-{timezone.now().strftime('%Y%m')}-{last_num + 1:04d}"
    je = JournalEntry.objects.create(
        entry_number=entry_number,
        date=expense.expense_date,
        description=f"Expense - {expense.description[:50]}",
        is_posted=True, created_by=created_by,
    )
    JournalLine.objects.create(
        journal_entry=je, account=acc_expense,
        description=expense.description[:100],
        debit=expense.amount_excl, credit=Decimal('0'),
    )
    if expense.vat_amount > 0:
        JournalLine.objects.create(
            journal_entry=je, account=acc_vat,
            description=f"VAT on {expense.description[:50]}",
            debit=expense.vat_amount, credit=Decimal('0'),
        )
    JournalLine.objects.create(
        journal_entry=je, account=acc_ap,
        description=f"Expense payable - {expense.description[:50]}",
        debit=Decimal('0'), credit=expense.amount_incl,
    )


def auto_post_expense_payment(expense, amount, created_by=None):
    acc_bank = Account.objects.filter(code='1000').first()
    acc_ap = Account.objects.filter(code='2000').first()
    if not all([acc_bank, acc_ap]):
        return
    last_num = JournalEntry.objects.count()
    entry_number = f"EPAY-{timezone.now().strftime('%Y%m')}-{last_num + 1:04d}"
    je = JournalEntry.objects.create(
        entry_number=entry_number,
        date=timezone.now().date(),
        description=f"Expense payment - {expense.description[:50]}",
        is_posted=True, created_by=created_by,
    )
    JournalLine.objects.create(
        journal_entry=je, account=acc_ap,
        description=f"Pay {expense.description[:50]}",
        debit=amount, credit=Decimal('0'),
    )
    JournalLine.objects.create(
        journal_entry=je, account=acc_bank,
        description=f"EFT - {expense.description[:50]}",
        debit=Decimal('0'), credit=amount,
    )


def auto_post_invoice(invoice, created_by=None):
    """Auto-create journal entry when an invoice is issued."""
    acc_receivables = Account.objects.filter(code='1100').first()
    acc_income = Account.objects.filter(code='4000').first()
    acc_vat = Account.objects.filter(code='2100').first()

    if not all([acc_receivables, acc_income, acc_vat]):
        return

    last_num = JournalEntry.objects.count()
    entry_number = f"INV-{timezone.now().strftime('%Y%m')}-{last_num + 1:04d}"

    je = JournalEntry.objects.create(
        entry_number=entry_number,
        date=invoice.issue_date,
        description=f"Invoice {invoice.invoice_number} - {invoice.exhibitor.company_name}",
        is_posted=True,
        created_by=created_by,
    )

    JournalLine.objects.create(
        journal_entry=je, account=acc_receivables,
        description=f"Stall rental - {invoice.booking.booking_reference}",
        debit=invoice.amount_incl, credit=Decimal('0'),
    )

    JournalLine.objects.create(
        journal_entry=je, account=acc_income,
        description=f"Stall rental income",
        debit=Decimal('0'), credit=invoice.amount_excl,
    )

    JournalLine.objects.create(
        journal_entry=je, account=acc_vat,
        description=f"VAT on stall rental",
        debit=Decimal('0'), credit=invoice.vat_amount,
    )


def auto_post_discount(booking, discount_amount, created_by=None):
    """Auto-create journal entry when a discount is fully approved."""
    acc_discount = Account.objects.filter(code='4600').first()
    acc_income = Account.objects.filter(code='4000').first()
    if not all([acc_discount, acc_income]):
        return
    last_num = JournalEntry.objects.count()
    entry_number = f"DSC-{timezone.now().strftime('%Y%m')}-{last_num + 1:04d}"
    je = JournalEntry.objects.create(
        entry_number=entry_number,
        date=timezone.now().date(),
        description=f"Discount approved - {booking.booking_reference} - R{discount_amount}",
        is_posted=True, created_by=created_by,
    )
    JournalLine.objects.create(
        journal_entry=je, account=acc_discount,
        description=f"Discount for {booking.booking_reference}",
        debit=discount_amount, credit=0,
    )
    JournalLine.objects.create(
        journal_entry=je, account=acc_income,
        description=f"Less: Discount on {booking.booking_reference}",
        debit=0, credit=discount_amount,
    )


def auto_post_accepted_quotation(quotation, expense, created_by=None):
    """Auto-create journal entry when a quotation is accepted (creates liability/expense)."""
    acc_expense = Account.objects.filter(code='5000').first()
    acc_vat = Account.objects.filter(code='2100').first()
    acc_ap = Account.objects.filter(code='2000').first()
    if not all([acc_expense, acc_vat, acc_ap]):
        return
    provider_name = quotation.provider.company_name if quotation.provider else (quotation.submitter_company_name or 'Unknown')
    last_num = JournalEntry.objects.count()
    entry_number = f"ACC-{timezone.now().strftime('%Y%m')}-{last_num + 1:04d}"
    je = JournalEntry.objects.create(
        entry_number=entry_number,
        date=timezone.now().date(),
        description=f"Accepted Quotation {quotation.quotation_number} - {provider_name}",
        is_posted=True, created_by=created_by,
    )
    JournalLine.objects.create(
        journal_entry=je, account=acc_expense,
        description=f"{quotation.rfq.title[:100]} - {provider_name}",
        debit=quotation.total_amount_excl, credit=Decimal('0'),
    )
    if quotation.vat_amount > 0:
        JournalLine.objects.create(
            journal_entry=je, account=acc_vat,
            description=f"VAT on {quotation.quotation_number}",
            debit=quotation.vat_amount, credit=Decimal('0'),
        )
    JournalLine.objects.create(
        journal_entry=je, account=acc_ap,
        description=f"Payable - {quotation.quotation_number} - {provider_name}",
        debit=Decimal('0'), credit=quotation.total_amount_incl,
    )


def auto_post_payment(payment, created_by=None):
    """Auto-create journal entry when a payment is verified."""
    acc_bank = Account.objects.filter(code='1000').first()
    acc_receivables = Account.objects.filter(code='1100').first()

    if not all([acc_bank, acc_receivables]):
        return

    last_num = JournalEntry.objects.count()
    entry_number = f"PAY-{timezone.now().strftime('%Y%m')}-{last_num + 1:04d}"

    inv = payment.invoice
    date = payment.verified_at.date() if payment.verified_at else timezone.now().date()

    je = JournalEntry.objects.create(
        entry_number=entry_number,
        date=date,
        description=f"Payment {payment.receipt_number} - {inv.invoice_number}",
        is_posted=True,
        created_by=created_by,
    )

    JournalLine.objects.create(
        journal_entry=je, account=acc_bank,
        description=f"Payment received - {inv.invoice_number}",
        debit=payment.amount, credit=Decimal('0'),
    )

    JournalLine.objects.create(
        journal_entry=je, account=acc_receivables,
        description=f"Settle invoice {inv.invoice_number}",
        debit=Decimal('0'), credit=payment.amount,
    )
