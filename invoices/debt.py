from decimal import Decimal
from django.utils import timezone
from .models import DebtDeclaration, DebtPaymentSchedule, Payment, LedgerEntry, Receipt


def get_exhibitor_outstanding(exhibitor):
    """Sum of outstanding balances on the exhibitor's open invoices."""
    from .models import Invoice
    from django.db.models import Sum
    return Invoice.objects.filter(
        exhibitor=exhibitor,
    ).exclude(status__in=['paid', 'cancelled']).aggregate(
        t=Sum('balance_due')
    )['t'] or Decimal('0')


def refresh_schedule_status(declaration):
    """Flag any past-due pending schedule lines as missed. Returns True if any changed."""
    today = timezone.localdate()
    changed = False
    for s in DebtPaymentSchedule.objects.filter(declaration=declaration, status='pending'):
        if s.due_date < today:
            s.status = 'missed'
            s.save(update_fields=['status'])
            changed = True
    return changed


def maybe_default_declaration(declaration, notify=True):
    """If every scheduled date has passed unpaid (no payments at all), mark as defaulted.

    Returns True when the declaration transitions to defaulted.
    """
    refresh_schedule_status(declaration)
    schedules = list(DebtPaymentSchedule.objects.filter(declaration=declaration))
    if (
        declaration.status == 'active'
        and schedules
        and not any(s.status == 'paid' for s in schedules)
        and all(s.status == 'missed' for s in schedules)
    ):
        declaration.status = 'defaulted'
        declaration.defaulted_at = timezone.now()
        declaration.save(update_fields=['status', 'defaulted_at'])
        if notify:
            from notifications.utils import (
                send_debt_declaration_defaulted,
                send_debt_declaration_defaulted_exhibitor,
            )
            send_debt_declaration_defaulted(declaration)
            send_debt_declaration_defaulted_exhibitor(declaration)
        return True
    return False


def maybe_complete_declaration(declaration):
    """Mark a declaration completed once every scheduled date has been paid."""
    if (
        declaration.status in ('active',)
        and declaration.payment_schedules.exists()
        and not declaration.payment_schedules.exclude(status='paid').exists()
    ):
        declaration.status = 'completed'
        declaration.save(update_fields=['status'])
        return True
    return False


def apply_declaration_payment(schedule, payment_method, remark, user):
    """Record a schedule date as paid, applying the cash to the exhibitor's open invoices.

    Follows the same accounting flow as `verify_payment`: creates verified Payment(s),
    updates invoice + booking balances, issues a Receipt and LedgerEntry, and auto-posts
    the double-entry (Dr Bank / Cr Receivables).
    """
    declaration = schedule.declaration
    exhibitor = declaration.exhibitor
    amount = schedule.amount
    if amount <= 0:
        return []

    applied = 0
    payments = []
    from .models import Invoice
    open_invoices = Invoice.objects.filter(
        exhibitor=exhibitor,
    ).exclude(status__in=['paid', 'cancelled']).filter(
        balance_due__gt=0,
    ).order_by('issue_date', 'id')

    for inv in open_invoices:
        if applied >= amount:
            break
        alloc = min(inv.balance_due, amount - applied)
        if alloc <= 0:
            continue

        payment = Payment.objects.create(
            invoice=inv,
            booking=inv.display_booking,
            amount=alloc,
            payment_method=payment_method,
            reference_number='',
            status='verified',
            verified_by=user,
            verified_at=timezone.now(),
            notes=f'Debt declaration {declaration.declaration_number} - schedule {schedule.due_date}',
            receipt_number=f"RCT-{__import__('uuid').uuid4().hex[:8].upper()}",
        )

        from .views import refresh_invoice
        refresh_invoice(inv)

        receipt = Receipt.objects.create(
            receipt_number=payment.receipt_number,
            payment=payment,
            exhibitor=exhibitor,
            amount=alloc,
            payment_method=payment_method,
            reference_number='',
            issue_date=timezone.localdate(),
            notes=remark or f'Debt declaration {declaration.declaration_number}',
        )

        booking = inv.display_booking
        if booking is not None:
            LedgerEntry.objects.create(
                exhibitor=exhibitor,
                booking=booking,
                entry_type='payment',
                description=f'Payment received - {inv.invoice_number}',
                reference=receipt.receipt_number,
                debit=0,
                credit=alloc,
                balance=inv.balance_due,
                entry_date=timezone.now().date(),
            )

        from accounting.auto_post import auto_post_payment
        auto_post_payment(payment, created_by=user)

        applied += alloc
        payments.append(payment)

    if not payments:
        return []

    schedule.status = 'paid'
    schedule.paid_at = timezone.now()
    schedule.marked_by = user
    schedule.remark = remark or f'Paid via {payment_method.upper()}'
    schedule.save(update_fields=['status', 'paid_at', 'marked_by', 'remark'])

    maybe_complete_declaration(declaration)
    return payments