from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Sum, Q
from django.utils import timezone
from decimal import Decimal
from .models import Account, JournalEntry, JournalLine
from .forms import JournalEntryForm, JournalLineForm
from invoices.models import Invoice, Payment
from portal.views import erp_login_required, erp_section_required


@erp_section_required('accounting')
def dashboard(request):
    income_accounts = Account.objects.filter(type='income')
    expense_accounts = Account.objects.filter(type='expense')
    asset_accounts = Account.objects.filter(type='asset')
    liability_accounts = Account.objects.filter(type='liability')

    total_income = sum(acc.balance() for acc in income_accounts)
    total_expenses = sum(acc.balance() for acc in expense_accounts)
    net_profit = total_income - total_expenses
    total_receivables = Invoice.objects.filter(status__in=('sent', 'partial', 'overdue')).aggregate(
        total=Sum('balance_due'))['total'] or Decimal('0')
    total_collected = Payment.objects.filter(status='verified').aggregate(
        total=Sum('amount'))['total'] or Decimal('0')
    pending_payments = Payment.objects.filter(status='pending').count()
    unpaid_invoices = Invoice.objects.filter(status__in=('sent', 'partial', 'overdue')).count()

    # Provider expense tracking
    from providers.models import Expense as ProviderExpense
    total_expense_incurred = ProviderExpense.objects.aggregate(
        total=Sum('amount_incl'))['total'] or Decimal('0')
    total_paid_to_providers = ProviderExpense.objects.aggregate(
        total=Sum('amount_paid'))['total'] or Decimal('0')
    total_unpaid_expenses = ProviderExpense.objects.filter(
        status__in=('unpaid', 'partial')).aggregate(
        total=Sum('balance_due'))['total'] or Decimal('0')
    unpaid_expense_count = ProviderExpense.objects.filter(status__in=('unpaid', 'partial')).count()

    recent_entries = JournalEntry.objects.select_related('created_by').prefetch_related('lines__account')[:15]

    monthly_income = JournalLine.objects.filter(
        account__type='income', journal_entry__is_posted=True,
    ).values('journal_entry__date__month', 'journal_entry__date__year').annotate(
        total=Sum('credit')
    ).order_by('-journal_entry__date__year', '-journal_entry__date__month')[:12]

    return render(request, 'accounting/dashboard.html', {
        'total_income': total_income,
        'total_expenses': total_expenses,
        'net_profit': net_profit,
        'total_receivables': total_receivables,
        'total_collected': total_collected,
        'pending_payments': pending_payments,
        'unpaid_invoices': unpaid_invoices,
        'total_expense_incurred': total_expense_incurred,
        'total_paid_to_providers': total_paid_to_providers,
        'total_unpaid_expenses': total_unpaid_expenses,
        'unpaid_expense_count': unpaid_expense_count,
        'recent_entries': recent_entries,
        'monthly_income': monthly_income,
    })


@erp_section_required('accounting')
def chart_of_accounts(request):
    accounts = Account.objects.all()
    account_types = ['asset', 'liability', 'equity', 'income', 'expense']
    grouped = []
    for atype in account_types:
        accs = [a for a in accounts if a.type == atype]
        total = sum(a.balance() for a in accs)
        grouped.append({'type': atype, 'accounts': accs, 'total': total})
    return render(request, 'accounting/chart_of_accounts.html', {
        'grouped': grouped,
    })


@erp_section_required('accounting')
def journal_entries(request):
    entries = JournalEntry.objects.select_related('created_by').prefetch_related('lines__account').order_by('-date', '-created_at')
    return render(request, 'accounting/journal_entries.html', {
        'entries': entries,
    })


@erp_section_required('accounting')
def create_journal_entry(request):
    if request.method == 'POST':
        form = JournalEntryForm(request.POST)
        if form.is_valid():
            je = form.save(commit=False)
            je.created_by = request.user
            last_num = JournalEntry.objects.count()
            je.entry_number = f"JE-{timezone.now().strftime('%Y%m')}-{last_num + 1:04d}"
            je.save()
            messages.success(request, f'Journal entry {je.entry_number} created. Add lines below.')
            return redirect('accounting:journal_entries')
    else:
        form = JournalEntryForm()
    return render(request, 'accounting/journal_entries.html', {
        'form': form,
        'accounts': Account.objects.filter(is_active=True),
    })


@erp_section_required('accounting')
def add_journal_line(request, entry_id):
    je = get_object_or_404(JournalEntry, pk=entry_id)
    if request.method == 'POST':
        form = JournalLineForm(request.POST)
        if form.is_valid():
            JournalLine.objects.create(
                journal_entry=je,
                account=form.cleaned_data['account'],
                description=form.cleaned_data['description'],
                debit=form.cleaned_data['debit'] or Decimal('0'),
                credit=form.cleaned_data['credit'] or Decimal('0'),
            )
            messages.success(request, 'Line added.')
        else:
            messages.error(request, 'Invalid line data.')
    return redirect('accounting:journal_entries')


@erp_section_required('accounting')
def trial_balance(request):
    accounts = Account.objects.filter(is_active=True).order_by('code')
    tb_data = []
    total_dr = Decimal('0')
    total_cr = Decimal('0')
    for acc in accounts:
        dr = acc.lines.aggregate(Sum('debit'))['debit__sum'] or Decimal('0')
        cr = acc.lines.aggregate(Sum('credit'))['credit__sum'] or Decimal('0')
        if acc.type in ['asset', 'expense']:
            balance = dr - cr
            dr_show = balance if balance > 0 else Decimal('0')
            cr_show = abs(balance) if balance < 0 else Decimal('0')
        else:
            balance = cr - dr
            dr_show = abs(balance) if balance < 0 else Decimal('0')
            cr_show = balance if balance > 0 else Decimal('0')
        total_dr += dr_show
        total_cr += cr_show
        tb_data.append({
            'account': acc,
            'debit': dr_show,
            'credit': cr_show,
        })
    return render(request, 'accounting/trial_balance.html', {
        'tb_data': tb_data,
        'total_dr': total_dr,
        'total_cr': total_cr,
    })


def _ledger_balance(account, date_from=None, date_to=None):
    """Balance of an account from its journal lines, optionally date-filtered.

    For income accounts returns credits - debits; for expense accounts debits - credits,
    matching Account.balance() semantics so ledger figures stay consistent elsewhere.
    """
    lines = account.lines.all()
    if date_from:
        lines = lines.filter(journal_entry__date__gte=date_from)
    if date_to:
        lines = lines.filter(journal_entry__date__lte=date_to)
    dr = lines.aggregate(Sum('debit'))['debit__sum'] or Decimal('0')
    cr = lines.aggregate(Sum('credit'))['credit__sum'] or Decimal('0')
    if account.type == 'expense':
        return dr - cr
    return cr - dr


@erp_section_required('accounting')
def income_statement(request):
    from bookings.models import Booking
    from events.models import Event
    from django.utils.dateparse import parse_date

    events = Event.objects.order_by('start_date')
    event_id = request.GET.get('event_id', '')
    active_event = events.filter(pk=event_id).first() if event_id else None
    start_date = request.GET.get('start_date') or ''
    end_date = request.GET.get('end_date') or ''
    date_from = parse_date(start_date) if start_date else None
    date_to = parse_date(end_date) if end_date else None

    income_accounts = Account.objects.filter(type='income', is_active=True)
    expense_accounts = Account.objects.filter(type='expense', is_active=True)

    incomes = []
    expenses = []
    reconciliation = None

    if active_event:
        stall_acc = Account.objects.filter(code='4000').first()
        sold_statuses = ['pending', 'approved', 'confirmed', 'completed']
        sold_bks = Booking.objects.filter(event=active_event, status__in=sold_statuses)
        stall_revenue = sold_bks.aggregate(s=Sum('total_amount'))['s'] or Decimal('0')
        if stall_acc and stall_revenue > 0:
            incomes.append({
                'account': stall_acc,
                'amount': stall_revenue,
                'basis': 'VAT-inclusive, from bookings',
            })
        discounts = Decimal('0')
        for bk in sold_bks.prefetch_related('discount_requests'):
            for d in bk.discount_requests.filter(status='approved'):
                discounts += d.discount_amount
        reconciliation = {
            'event': active_event,
            'stalls_sold': sold_bks.count(),
            'sales_amount': sold_bks.aggregate(s=Sum('stall_price'))['s'] or Decimal('0'),
            'discounts': discounts,
            'revenue': stall_revenue,
            'received': sold_bks.aggregate(s=Sum('amount_paid'))['s'] or Decimal('0'),
            'outstanding': sold_bks.aggregate(s=Sum('balance_due'))['s'] or Decimal('0'),
        }
        for acc in income_accounts:
            if acc.code == '4000':
                continue
            bal = _ledger_balance(acc, date_from, date_to)
            if bal > 0:
                incomes.append({'account': acc, 'amount': bal, 'basis': 'Ledger (VAT-exclusive)'})
    else:
        for acc in income_accounts:
            bal = _ledger_balance(acc, date_from, date_to)
            if bal > 0:
                incomes.append({'account': acc, 'amount': bal, 'basis': 'Ledger (VAT-exclusive)'})

    for acc in expense_accounts:
        bal = _ledger_balance(acc, date_from, date_to)
        if bal > 0:
            expenses.append({'account': acc, 'amount': bal})

    total_income = sum(i['amount'] for i in incomes)
    total_expenses = sum(e['amount'] for e in expenses)
    net_profit = total_income - total_expenses
    return render(request, 'accounting/income_statement.html', {
        'events': events,
        'active_event': active_event,
        'start_date': start_date,
        'end_date': end_date,
        'incomes': incomes,
        'expenses': expenses,
        'total_income': total_income,
        'total_expenses': total_expenses,
        'net_profit': net_profit,
        'reconciliation': reconciliation,
    })


@erp_section_required('accounting')
def balance_sheet(request):
    asset_accounts = Account.objects.filter(type='asset', is_active=True)
    liability_accounts = Account.objects.filter(type='liability', is_active=True)
    equity_accounts = Account.objects.filter(type='equity', is_active=True)
    income_accounts = Account.objects.filter(type='income', is_active=True)
    expense_accounts = Account.objects.filter(type='expense', is_active=True)

    assets = [{'account': a, 'amount': a.balance()} for a in asset_accounts if a.balance() != 0]
    liabilities = [{'account': a, 'amount': a.balance()} for a in liability_accounts if a.balance() != 0]
    equities = [{'account': a, 'amount': a.balance()} for a in equity_accounts if a.balance() != 0]

    total_income = sum(a.balance() for a in income_accounts)
    total_expenses = sum(a.balance() for a in expense_accounts)
    current_pl = total_income - total_expenses

    total_assets = sum(a['amount'] for a in assets)
    total_liabilities = sum(l['amount'] for l in liabilities)
    total_equity = sum(e['amount'] for e in equities) + current_pl

    total_liabilities_equity = total_liabilities + total_equity
    return render(request, 'accounting/balance_sheet.html', {
        'assets': assets,
        'liabilities': liabilities,
        'equities': equities,
        'total_assets': total_assets,
        'total_liabilities': total_liabilities,
        'total_equity': total_equity,
        'total_liabilities_equity': total_liabilities_equity,
        'current_pl': current_pl,
    })
