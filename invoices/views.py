from decimal import Decimal
import uuid
from datetime import timedelta
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Invoice, InvoiceLine, Payment, Receipt, LedgerEntry
from bookings.models import Booking
from bookings.pricing import booking_totals
from django.utils import timezone
from django.db.models import Sum, Q
from notifications.utils import send_invoice_email, send_payment_received


def _manual_discount(stall_price, invoice):
    """Manual staff-applied discount for one stand: a percentage of the stand price
    only (excludes electricity deposit, accessories and VAT)."""
    pct = (invoice.discount_percent or Decimal('0')) if invoice is not None else Decimal('0')
    if not pct:
        return Decimal('0')
    return (Decimal(stall_price or 0) * pct / Decimal('100')).quantize(Decimal('0.01'))


def booking_amount_incl(booking, invoice=None):
    elec_dep = booking.electricity_deposit if booking.requires_power else Decimal('0')
    amount_incl, vat_amount = booking_totals(booking.stall_price, elec_dep, booking.accessories_total, 0)
    if invoice is None:
        line = getattr(booking, 'invoice_line', None)
        invoice = line.invoice if line is not None else None
    discount = (booking.early_payment_discount or Decimal('0')) + _manual_discount(booking.stall_price, invoice)
    return amount_incl - discount, vat_amount


# Early full-payment discounts: 5% of stand price if the stand is fully paid by
# 30 Sep 2026; otherwise 2.5% if fully paid by 31 Oct 2026. Never combined (max one tier).
EARLY_5_DEADLINE = __import__('datetime').date(2026, 9, 30)
EARLY_25_DEADLINE = __import__('datetime').date(2027, 10, 15)

# Coverage is measured against the stand price; allow a small rounding tolerance
# so a stand paid the discounted amount rounded to the nearest rand (e.g. R44 911
# instead of R44 911.25) still qualifies for the discount.
DISCOUNT_TOLERANCE = Decimal('1.00')


def evaluate_early_payment_discount(booking):
    """Assess tiered early-payment discount for a booking based on verified
    payments attributed to it. Single tier only (5% XOR 2.5%)."""
    from invoices.models import Payment
    line = getattr(booking, 'invoice_line', None)
    inv = line.invoice if line is not None else booking.invoices.first()
    if inv is None:
        return Decimal('0')
    return evaluate_invoice_discounts(inv).get(booking.id, Decimal('0'))


def evaluate_invoice_discounts(invoice):
    """Evaluate early-payment discounts for every booking on an invoice.

    A payment can only fund ONE stand: payments tagged to a booking count
    toward that booking only; untagged payments (booking=None) are consumed
    once across bookings of the same invoice (in booking order), so the same
    money can never trigger two discounts. Within each stand, the tier is
    fixed by the date cumulative verified payments first reached that
    stand's price (5% if on/before 30 Sep 2026, 2.5% if on/before 31 Oct
    2026, never both).
    """
    import datetime as _dt
    from invoices.models import Payment
    payments = list(Payment.objects.filter(invoice=invoice, status='verified').order_by('payment_date'))
    tagged = {}
    untagged = []
    for p in payments:
        if p.booking_id:
            tagged.setdefault(p.booking_id, []).append(p)
        else:
            untagged.append(p)
    from datetime import timedelta
    results = {}
    for line in invoice.billable_lines.select_related('booking').all():
        b = line.booking
        if b is None:
            continue
        pool = list(tagged.get(b.id, [])) + list(untagged)
        stall = Decimal(b.stall_price or 0)
        target = stall
        # Eligibility is based strictly on STALL PRICE coverage (ignore deposit/accessories).
        # - verified payments totaling >= 95% of stall price by 30 Sep 2026 (+5 day grace) → 5%
        # - verified payments totaling >= 97.5% of stall price by 31 Oct 2026 (+5 day grace) → 2.5%
        coverage_95_date = None
        coverage_975_date = None
        covered = Decimal('0')
        consumed = []
        for p in sorted(pool, key=lambda x: x.payment_date or _dt.datetime.max):
            covered += p.amount
            if p.booking_id is None:
                consumed.append(p)
            if coverage_95_date is None and covered >= stall * Decimal('0.95') - DISCOUNT_TOLERANCE:
                coverage_95_date = p.payment_date.date() if p.payment_date else None
            if coverage_975_date is None and covered >= stall * Decimal('0.975') - DISCOUNT_TOLERANCE:
                coverage_975_date = p.payment_date.date() if p.payment_date else None
            if coverage_95_date is not None and coverage_975_date is not None:
                break
        for p in consumed:
            if p in untagged:
                untagged.remove(p)
        discount = Decimal('0')
        tier = ''
        if stall > 0:
            grace = timedelta(days=5)
            if coverage_95_date is not None and coverage_95_date <= EARLY_5_DEADLINE + grace:
                discount = (stall * Decimal('0.05')).quantize(Decimal('0.01')); tier = '5'
            elif coverage_975_date is not None and coverage_975_date <= EARLY_25_DEADLINE + grace:
                discount = (stall * Decimal('0.025')).quantize(Decimal('0.01')); tier = '2.5'
        b.early_payment_discount = discount
        b.early_payment_tier = tier
        manual = _manual_discount(b.stall_price, invoice)
        b.total_amount = (b.subtotal or Decimal('0')) - discount - manual
        b.balance_due = b.total_amount - (b.amount_paid or Decimal('0'))
        b.save(update_fields=['early_payment_discount', 'early_payment_tier', 'total_amount', 'balance_due'])
        results[b.id] = discount
    return results


def _stall_description(booking):
    name = booking.stall.name if booking.stall else '-'
    zone = booking.stall.zone if booking.stall and booking.stall.zone else ''
    size = ''
    if booking.stall and booking.stall.width and booking.stall.height:
        size = f" ({float(booking.stall.width) / 1000:.1f}x{float(booking.stall.height) / 1000:.1f}m)"
    return f"Stall {name}{size}" + (f" - {zone}" if zone else "")


def _set_line(inv, booking):
    """Create or update the consolidated invoice line for a booking, reassigning to inv if moved."""
    line = InvoiceLine.objects.filter(booking=booking).first()
    if line is None:
        line = InvoiceLine(invoice=inv, booking=booking)
    elif line.invoice_id != inv.id:
        old_inv = line.invoice
        line.invoice = inv
        line.save(update_fields=['invoice'])
        refresh_invoice(old_inv)
    amount_incl, vat = booking_amount_incl(booking, inv)
    line.description = _stall_description(booking)
    line.amount_excl = amount_incl - vat
    line.vat_amount = vat
    line.amount_incl = amount_incl
    line.save()
    return line


def refresh_invoice(inv):
    """Recompute a consolidated invoice from its lines + verified payments, then sync each line booking."""
    lines = list(inv.billable_lines.select_related('booking').all())
    amount_excl = sum((l.amount_excl or 0) for l in lines)
    vat_amount = sum((l.vat_amount or 0) for l in lines)
    incl = sum((l.amount_incl or 0) for l in lines)
    paid = inv.payments.filter(status='verified').aggregate(s=Sum('amount'))['s'] or Decimal('0')
    inv.amount_excl = amount_excl
    inv.vat_amount = vat_amount
    inv.amount_incl = incl
    inv.amount_paid = paid
    inv.balance_due = incl - paid
    inv.discount_amount = sum(
        (_manual_discount(l.booking.stall_price, inv) for l in lines if l.booking),
        Decimal('0'),
    )
    if not lines:
        inv.status = 'draft'
        inv.paid_date = None
    elif inv.balance_due <= 0:
        inv.status = 'paid'
        inv.paid_date = inv.paid_date or timezone.localdate()
    elif paid > 0:
        inv.status = 'partial'
        inv.paid_date = None
    else:
        inv.status = 'sent'
        inv.paid_date = None
    inv.save()
    remaining = paid
    for l in lines:
        b = l.booking
        alloc = min(l.amount_incl, remaining) if remaining > 0 else Decimal('0')
        b.amount_paid = alloc
        b.balance_due = l.amount_incl - alloc
        if alloc >= l.amount_incl:
            b.payment_status = 'paid'
            if b.status in ('pending', 'approved'):
                b.status = 'confirmed'
                b.confirmed_date = timezone.now()
                if b.stall_id:
                    b.stall.status = 'confirmed'
                    b.stall.save(update_fields=['status'])
        elif alloc > 0:
            b.payment_status = 'partial'
        else:
            b.payment_status = 'unpaid'
        b.save(update_fields=['amount_paid', 'balance_due', 'payment_status', 'status', 'confirmed_date'])
        remaining = max(remaining - l.amount_incl, Decimal('0'))
    return inv


def ensure_booking_invoice(booking):
    """Attach an authorized booking to the exhibitor's consolidated active invoice for its event; create one if needed."""
    line = InvoiceLine.objects.filter(booking=booking).first()
    inv = line.invoice if line else None
    created = False
    if inv is None:
        inv = Invoice.objects.filter(
            exhibitor=booking.exhibitor, event=booking.event
        ).exclude(status__in=['paid', 'cancelled']).order_by('-id').first()
    if inv is None:
        inv = Invoice.objects.create(
            invoice_number=f"INV-{uuid.uuid4().hex[:8].upper()}",
            booking=booking,
            event=booking.event,
            exhibitor=booking.exhibitor,
            amount_excl=0, vat_amount=0, amount_incl=0, amount_paid=0, balance_due=0,
            status='sent',
            issue_date=timezone.localdate(),
            due_date=timezone.localdate() + timedelta(days=30),
        )
        created = True
    if not inv.booking:
        inv.booking = booking
        inv.save(update_fields=['booking'])
    _set_line(inv, booking)
    return refresh_invoice(inv), created


def update_invoice_from_booking(booking):
    """Recalculate the booking's consolidated invoice after requirements/accessories change."""
    line = InvoiceLine.objects.filter(booking=booking).first()
    if line is None:
        return None
    if booking.status == 'cancelled':
        # Cancelled stands are not billed: never re-price their line, keep it zeroed
        # and labelled so a payment edit/recalc cannot resurrect the charge.
        if line.amount_incl or line.amount_excl or line.vat_amount:
            if not line.description.startswith('CANCELLED -'):
                line.description = f"CANCELLED - {line.description}"
            line.amount_excl = Decimal('0')
            line.vat_amount = Decimal('0')
            line.amount_incl = Decimal('0')
            line.save(update_fields=['description', 'amount_excl', 'vat_amount', 'amount_incl'])
        return refresh_invoice(line.invoice)
    amount_incl, vat = booking_amount_incl(booking, line.invoice)
    line.description = _stall_description(booking)
    line.amount_excl = amount_incl - vat
    line.vat_amount = vat
    line.amount_incl = amount_incl
    line.save()
    return refresh_invoice(line.invoice)


@login_required
def my_invoices(request):
    invoices = request.user.invoices.all().select_related('event').prefetch_related('invoice_lines__booking__stall')
    return render(request, 'invoices/list.html', {'invoices': invoices})


@login_required
def invoice_detail(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, exhibitor=request.user)
    refresh_invoice(invoice)
    invoice.refresh_from_db()
    payments = invoice.payments.all()
    return render(request, 'invoices/detail.html', {
        'invoice': invoice,
        'payments': payments,
    })


@login_required
def make_payment(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, exhibitor=request.user)
    refresh_invoice(invoice)
    invoice.refresh_from_db()
    if request.method == 'POST':
        from decimal import Decimal, InvalidOperation
        amount_raw = request.POST.get('amount', '').strip()
        try:
            amount = Decimal(amount_raw)
        except InvalidOperation:
            amount = Decimal('0')
        if amount <= 0:
            messages.error(request, 'Please enter a valid payment amount.')
            return redirect('make_payment', pk=pk)
        ref = request.POST.get('reference_number', '').strip()
        method = request.POST.get('payment_method', 'eft')
        pop = request.FILES.get('proof_of_payment')
        pay_booking = None
        bid = request.POST.get('booking_id')
        if bid:
            pay_booking = Booking.objects.filter(pk=bid, invoice_line__invoice=invoice).first()
        payment = Payment.objects.create(
            invoice=invoice,
            booking=pay_booking or invoice.display_booking,
            amount=amount,
            payment_method=method,
            reference_number=ref,
            proof_of_payment=pop,
        )
        send_payment_received(payment)
        return redirect('payment_completed', pk=payment.pk)
    return render(request, 'invoices/pay.html', {'invoice': invoice})


@login_required
def payment_completed(request, pk):
    payment = get_object_or_404(Payment, pk=pk, invoice__exhibitor=request.user)
    return render(request, 'invoices/payment_completed.html', {'payment': payment})


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
def print_payments_receipt(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    if request.user != invoice.exhibitor and not request.user.is_staff:
        messages.error(request, 'Access denied.')
        return redirect('my_invoices')
    booking = invoice.display_booking
    payments = Payment.objects.filter(
        invoice=invoice, status='verified'
    ).select_related('invoice').order_by('payment_date')
    total_paid = payments.aggregate(s=Sum('amount'))['s'] or Decimal('0')
    return render(request, 'printouts/payments_receipt.html', {
        'booking': booking,
        'invoice': invoice,
        'payments': payments,
        'receipt': None,
        'total_paid': total_paid,
    })


@login_required
def account_statement(request):
    exhibitor = request.user
    entries = LedgerEntry.objects.filter(exhibitor=exhibitor).select_related('booking').order_by('entry_date', 'created_at')
    payment_notes = {}
    for p in Payment.objects.filter(invoice__exhibitor=exhibitor).select_related('receipt'):
        key = getattr(getattr(p, 'receipt', None), 'receipt_number', None) or p.reference_number
        if key:
            payment_notes.setdefault(key, p.notes)
    entries = list(entries)
    for e in entries:
        e.notes = payment_notes.get(e.reference, '') if e.entry_type == 'payment' else ''
    invoices = Invoice.objects.filter(exhibitor=exhibitor).order_by('issue_date')
    rows = []
    stand_balances = []
    total_invoiced = Decimal('0')
    total_paid = Decimal('0')
    for inv in invoices:
        refresh_invoice(inv)
        inv.refresh_from_db()
        lines = list(inv.billable_lines.select_related('booking__stall', 'booking__event'))
        total_invoiced += inv.amount_incl
        total_paid += inv.amount_paid
        rows.append({
            'invoice': inv,
            'lines': lines,
            'total': inv.amount_incl,
            'paid': inv.amount_paid,
            'balance': inv.balance_due,
        })
        for l in lines:
            b = l.booking
            stand_balances.append({
                'booking': b,
                'stall_name': b.stall.name if b.stall else '-',
                'fascia_name': b.fascia_name or '-',
                'event_name': b.event.name if b.event else '-',
                'total': l.amount_incl,
                'paid': b.amount_paid,
                'balance': b.balance_due,
            })
    outstanding = total_invoiced - total_paid
    total_credits = entries.filter(entry_type='payment').aggregate(s=Sum('credit'))['s'] or Decimal('0')
    total_debits = total_invoiced
    closing_balance = total_debits - total_credits
    today = timezone.localdate()
    aging_current = aging_30 = aging_60 = aging_90 = Decimal('0')
    for inv in Invoice.objects.filter(exhibitor=exhibitor, status__in=['sent', 'partial', 'overdue']):
        bal = inv.balance_due
        if bal > 0:
            days = (today - inv.due_date).days
            if days <= 0: aging_current += bal
            elif days <= 30: aging_30 += bal
            elif days <= 60: aging_60 += bal
            else: aging_90 += bal
    return render(request, 'printouts/statement.html', {
        'exhibitor': exhibitor, 'ledger': entries, 'invoice_rows': rows,
        'total_invoiced': total_invoiced, 'total_paid': total_paid,
        'outstanding': outstanding, 'overdue': aging_30 + aging_60 + aging_90,
        'total_debits': total_debits, 'total_credits': total_credits,
        'closing_balance': closing_balance,
        'aging_current': aging_current, 'aging_30': aging_30,
        'aging_60': aging_60, 'aging_90': aging_90,
        'stand_balances': stand_balances,
    })
