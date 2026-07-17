from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Invoice, Payment, Receipt, LedgerEntry
from django.utils import timezone
from django.db.models import Sum, Q
from notifications.utils import send_invoice_email, send_payment_received


def update_invoice_from_booking(booking):
    """Recalculate invoice amounts based on current booking state (accessories, requirements)."""
    invoices = booking.invoices.filter(status__in=['draft', 'sent', 'partial'])
    if not invoices.exists():
        return
    inv = invoices.first()
    elec_dep = booking.electricity_deposit if booking.requires_power else Decimal('0')
    amount_excl = booking.stall_price + booking.accessories_total + elec_dep
    vat_amount = amount_excl * Decimal('0.15')
    amount_incl = amount_excl + vat_amount
    verified = booking.payments.filter(status='verified').aggregate(s=Sum('amount'))['s'] or Decimal('0')
    inv.amount_excl = amount_excl
    inv.vat_amount = vat_amount
    inv.amount_incl = amount_incl
    inv.amount_paid = verified
    inv.balance_due = amount_incl - verified
    if inv.balance_due <= 0:
        inv.status = 'paid'
        inv.paid_date = timezone.now().date()
    elif verified > 0:
        inv.status = 'partial'
    else:
        inv.status = 'draft'
    inv.save()
    return inv


@login_required
def my_invoices(request):
    invoices = request.user.invoices.all().select_related('booking', 'booking__event')
    return render(request, 'invoices/list.html', {'invoices': invoices})


@login_required
def invoice_detail(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, exhibitor=request.user)
    update_invoice_from_booking(invoice.booking)
    invoice.refresh_from_db()
    payments = invoice.payments.all()
    return render(request, 'invoices/detail.html', {
        'invoice': invoice,
        'payments': payments,
    })


@login_required
def make_payment(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, exhibitor=request.user)
    update_invoice_from_booking(invoice.booking)
    invoice.refresh_from_db()
    if request.method == 'POST':
        amount = Decimal(request.POST.get('amount', '0'))
        ref = request.POST.get('reference_number', '')
        method = request.POST.get('payment_method', 'eft')
        pop = request.FILES.get('proof_of_payment')
        payment = Payment.objects.create(
            invoice=invoice,
            booking=invoice.booking,
            amount=amount,
            payment_method=method,
            reference_number=ref,
            proof_of_payment=pop,
        )
        messages.success(request, 'Payment submitted for verification.')
        send_payment_received(payment)
        return redirect('invoice_detail', pk=pk)
    return render(request, 'invoices/pay.html', {'invoice': invoice})


@login_required
def print_invoice(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    if request.user != invoice.exhibitor and not request.user.is_staff:
        messages.error(request, 'Access denied.')
        return redirect('my_invoices')
    return render(request, 'printouts/invoice.html', {'invoice': invoice})


@login_required
def print_receipt(request, pk):
    receipt = get_object_or_404(Receipt, pk=pk)
    if request.user != receipt.exhibitor and not request.user.is_staff:
        messages.error(request, 'Access denied.')
        return redirect('my_invoices')
    return render(request, 'printouts/receipt.html', {'receipt': receipt})


@login_required
def account_statement(request):
    exhibitor = request.user
    entries = LedgerEntry.objects.filter(exhibitor=exhibitor).select_related('booking').order_by('entry_date', 'created_at')
    total_invoiced = entries.filter(entry_type='invoice').aggregate(s=Sum('debit'))['s'] or 0
    total_paid = entries.filter(entry_type='payment').aggregate(s=Sum('credit'))['s'] or 0
    total_debits = entries.aggregate(s=Sum('debit'))['s'] or 0
    total_credits = entries.aggregate(s=Sum('credit'))['s'] or 0
    closing_balance = total_debits - total_credits
    outstanding = total_invoiced - total_paid
    today = timezone.now().date()
    aging_current = Decimal('0')
    aging_30 = Decimal('0')
    aging_60 = Decimal('0')
    aging_90 = Decimal('0')
    for inv in Invoice.objects.filter(exhibitor=exhibitor, status__in=['sent', 'partial', 'overdue']):
        bal = inv.balance_due
        if bal > 0:
            days = (today - inv.due_date).days
            if days <= 0:
                aging_current += bal
            elif days <= 30:
                aging_30 += bal
            elif days <= 60:
                aging_60 += bal
            else:
                aging_90 += bal
    return render(request, 'printouts/statement.html', {
        'exhibitor': exhibitor, 'ledger': entries,
        'total_invoiced': total_invoiced, 'total_paid': total_paid,
        'outstanding': outstanding, 'overdue': aging_30 + aging_60 + aging_90,
        'total_debits': total_debits, 'total_credits': total_credits,
        'closing_balance': closing_balance,
        'aging_current': aging_current, 'aging_30': aging_30,
        'aging_60': aging_60, 'aging_90': aging_90,
    })
