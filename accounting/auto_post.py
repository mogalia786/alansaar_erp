from django.utils import timezone
from django.db import IntegrityError, transaction
from decimal import Decimal
from .models import Account, JournalEntry, JournalLine


def _next_entry_number(prefix):
    """Return a unique journal entry number like 'PAY-202610-0007'.

    Uses the highest existing suffix for this prefix+month instead of a row
    count, so deleting entries can never cause a duplicate-key collision.
    """
    ym = timezone.now().strftime('%Y%m')
    base = f"{prefix}-{ym}-"
    highest = 0
    existing = JournalEntry.objects.filter(
        entry_number__startswith=base
    ).values_list('entry_number', flat=True)
    for number in existing:
        suffix = number[len(base):]
        if suffix.isdigit():
            highest = max(highest, int(suffix))
    return f"{base}{highest + 1:04d}"


def _create_journal_entry(prefix, date, description, created_by=None):
    """Create a journal entry with a collision-proof number, retrying on the
    rare race where a duplicate number is generated concurrently."""
    for _ in range(5):
        try:
            with transaction.atomic():
                return JournalEntry.objects.create(
                    entry_number=_next_entry_number(prefix),
                    date=date,
                    description=description,
                    is_posted=True,
                    created_by=created_by,
                )
        except IntegrityError:
            continue
    return JournalEntry.objects.create(
        entry_number=_next_entry_number(prefix),
        date=date,
        description=description,
        is_posted=True,
        created_by=created_by,
    )


def auto_post_expense(expense, created_by=None):
    acc_expense = Account.objects.filter(code='5000').first()
    acc_vat = Account.objects.filter(code='2100').first()
    acc_ap = Account.objects.filter(code='2000').first()
    if not all([acc_expense, acc_vat, acc_ap]):
        return
    je = _create_journal_entry(
        'EXP',
        expense.expense_date,
        f"Expense - {expense.description[:50]}",
        created_by=created_by,
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
    je = _create_journal_entry(
        'EPAY',
        timezone.now().date(),
        f"Expense payment - {expense.description[:50]}",
        created_by=created_by,
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

    ref = invoice.booking.booking_reference if invoice.booking else (
        invoice.invoice_lines.first().booking.booking_reference if invoice.invoice_lines.exists() else invoice.invoice_number
    )

    je = _create_journal_entry(
        'INV',
        invoice.issue_date,
        f"Invoice {invoice.invoice_number} - {invoice.exhibitor.company_name}",
        created_by=created_by,
    )

    JournalLine.objects.create(
        journal_entry=je, account=acc_receivables,
        description=f"Stall rental - {ref}",
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
    je = _create_journal_entry(
        'DSC',
        timezone.now().date(),
        f"Discount approved - {booking.booking_reference} - R{discount_amount}",
        created_by=created_by,
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
    je = _create_journal_entry(
        'ACC',
        timezone.now().date(),
        f"Accepted Quotation {quotation.quotation_number} - {provider_name}",
        created_by=created_by,
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

    inv = payment.invoice
    date = payment.payment_date.date() if payment.payment_date else (
        payment.verified_at.date() if payment.verified_at else timezone.now().date()
    )

    je = _create_journal_entry(
        'PAY',
        date,
        f"Payment {payment.receipt_number} - {inv.invoice_number}",
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


def auto_post_gate_taking(gate_taking, created_by=None):
    """Auto-create a balanced journal entry for cash collected at the gates.

    Debit the bank account for the full amount collected.
    Credit the 'Daily Gate Takings' income account (no VAT split).
    """
    acc_bank = Account.objects.filter(code='1000').first()
    acc_income = Account.objects.filter(code='4300').first()
    if not all([acc_bank, acc_income]):
        return

    je = _create_journal_entry(
        'GATE',
        gate_taking.date,
        f"Daily Gate Takings - {gate_taking.date}",
        created_by=created_by,
    )

    JournalLine.objects.create(
        journal_entry=je, account=acc_bank,
        description=f"Gate cash/card deposit - {gate_taking.date}",
        debit=gate_taking.total, credit=Decimal('0'),
    )

    JournalLine.objects.create(
        journal_entry=je, account=acc_income,
        description=f"Gate takings income - {gate_taking.date}",
        debit=Decimal('0'), credit=gate_taking.total,
    )

    gate_taking.journal_entry = je
    gate_taking.save(update_fields=['journal_entry'])
