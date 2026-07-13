from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Sum, Q
from django.utils import timezone
from django.http import StreamingHttpResponse
from decimal import Decimal
from .models import FNBAccount, FNBTransaction, FNBPaymentRecord
from .services import FNBStatementService, FNBPaymentService, LOG_STEPS
from providers.models import Expense, ServiceProvider
from invoices.models import Invoice


def bank_dashboard(request):
    accounts = FNBAccount.objects.filter(is_active=True)
    debtor_accounts = accounts.filter(account_type='debtor')
    creditor_accounts = accounts.filter(account_type='creditor')

    txns = FNBTransaction.objects.select_related('account').order_by('-transaction_date')[:50]
    payments = FNBPaymentRecord.objects.select_related('debtor_account', 'creditor_account').order_by('-initiated_at')[:20]

    total_debits = FNBTransaction.objects.aggregate(s=Sum('debit_amount'))['s'] or Decimal('0')
    total_credits = FNBTransaction.objects.aggregate(s=Sum('credit_amount'))['s'] or Decimal('0')

    context = {
        'debtor_accounts': debtor_accounts,
        'creditor_accounts': creditor_accounts,
        'transactions': txns,
        'payments': payments,
        'total_debits': total_debits,
        'total_credits': total_credits,
    }
    return render(request, 'fnb/bank_dashboard.html', context)


def bank_transactions(request):
    account_id = request.GET.get('account')
    qs = FNBTransaction.objects.select_related('account').order_by('-transaction_date')

    if account_id:
        qs = qs.filter(account_id=account_id)

    accounts = FNBAccount.objects.filter(is_active=True)
    total = qs.count()
    transactions = qs[:200]

    context = {
        'transactions': transactions,
        'accounts': accounts,
        'selected_account': int(account_id) if account_id else None,
        'total': total,
    }
    return render(request, 'fnb/bank_transactions.html', context)


def _check_mapped(txn):
    ref = (txn["reference"] or "").strip().upper()
    desc = (txn["description"] or "").strip().upper()
    is_credit = txn["credit_amount"] > 0

    if is_credit:
        if not ref:
            return None
        invoice = Invoice.objects.filter(invoice_number__iexact=ref).first()
        if invoice:
            return f"INV #{invoice.invoice_number}"
        from invoices.models import Payment as InvPayment
        payment = InvPayment.objects.filter(reference_number__iexact=ref).first()
        if payment:
            booking = payment.booking
            ref_label = getattr(booking, "booking_reference", "") or getattr(booking, "stand_number", "") if booking else ""
            return f"PAY #{payment.id} ({ref_label}) -> INV #{payment.invoice.invoice_number if payment.invoice else '?'}"
        if desc:
            payment = InvPayment.objects.filter(reference_number__icontains=desc[:20]).first()
            if payment:
                return f"PAY #{payment.id} (desc) -> INV #{payment.invoice.invoice_number if payment.invoice else '?'}"
        return None

    expense = Expense.objects.filter(payment_reference__iexact=ref).first()
    if expense:
        return f"EXP #{expense.id} ({expense.description[:30]})"
    expense = Expense.objects.filter(description__icontains=desc[:30]).first() if desc else None
    if expense:
        return f"EXP #{expense.id} (desc)"
    return None


def _format_balance(bal_data):
    if not bal_data:
        return None
    amount = bal_data.get("amountValue")
    return Decimal(str(amount)) if amount else None


def bank_sync_statements(request):
    log_steps = []
    fetched_transactions = None
    opening_balance = None
    closing_balance = None
    if request.method == 'POST':
        statement_date = request.POST.get('statement_date', '')
        account_number = request.POST.get('account_number', '')
        LOG_STEPS.clear()
        try:
            if not statement_date:
                raise ValueError("Statement date is required.")

            service = FNBStatementService()
            accounts_qs = FNBAccount.objects.filter(is_active=True, account_type='debtor')
            if account_number:
                accounts_qs = accounts_qs.filter(account_number=account_number)

            if not accounts_qs.exists():
                LOG_STEPS.append({"step": "No Accounts", "status": "error", "icon": "✗", "detail": "No active debtor accounts found."})
            else:
                total = 0
                all_fetched = []
                for account in accounts_qs:
                    try:
                        result = service.fetch_statement_range(account.account_number, statement_date)
                        if opening_balance is None:
                            opening_balance = _format_balance(result["opening_balance"])
                            closing_balance = _format_balance(result["closing_balance"])
                        txns = FNBStatementService.parse_entries(result["entries"])
                        LOG_STEPS.append({"step": f"Account {account.account_number}", "status": "pending", "icon": "…", "detail": f"{len(result['entries'])} entries, saving..."})
                        for txn in txns:
                            mapped_to = _check_mapped(txn)
                            obj, created = FNBTransaction.objects.get_or_create(
                                account=account,
                                transaction_date=txn["transaction_date"],
                                description=txn["description"],
                                debit_amount=txn["debit_amount"],
                                credit_amount=txn["credit_amount"],
                                defaults={
                                    "reference": txn["reference"],
                                    "balance": txn["balance"],
                                    "transaction_type": txn["transaction_type"],
                                    "mapped_to": mapped_to,
                                },
                            )
                            if not created and mapped_to and not obj.mapped_to:
                                obj.mapped_to = mapped_to
                                obj.save(update_fields=['mapped_to'])
                            all_fetched.append(obj)
                            if created:
                                total += 1
                        LOG_STEPS.append({"step": f"Account {account.account_number}", "status": "ok", "icon": "✓", "detail": f"Stored {total} new"})

                    except Exception as e:
                        LOG_STEPS.append({"step": f"Account {account.account_number}", "status": "error", "icon": "✗", "detail": str(e)})

                all_fetched.sort(key=lambda t: t.transaction_date)
                fetched_transactions = all_fetched
                LOG_STEPS.append({"step": "Complete", "status": "ok", "icon": "✓", "detail": f"Synced {total} new transaction(s)"})
                messages.success(request, f"Synced {total} new transactions.")

        except Exception as e:
            LOG_STEPS.append({"step": "Failed", "status": "error", "icon": "✗", "detail": str(e)})
            messages.error(request, f"Sync error: {e}")

        log_steps = list(LOG_STEPS)

    accounts = FNBAccount.objects.filter(is_active=True, account_type='debtor')
    return render(request, 'fnb/bank_sync.html', {
        'accounts': accounts,
        'log_steps': log_steps,
        'fetched_transactions': fetched_transactions,
        'opening_balance': opening_balance,
        'closing_balance': closing_balance,
    })

    def event_stream():
        import json, time
        html_log = ""
        all_fetched = []
        total = 0
        opening_balance = None
        closing_balance = None

        def emit(log_html):
            nonlocal html_log
            html_log += log_html
            data = json.dumps({"html": log_html})
            yield f"data: {data}\n\n"

        if not statement_date:
            yield from emit('<div class="mb-1 d-flex align-items-start gap-2" style="color:#f14c4c;"><span style="min-width:20px;">✗</span><span style="min-width:200px;color:#569cd6;">Validation</span><span style="color:#ce9178;">Statement date is required.</span></div>\n')
            return

        yield from emit(f'<div class="mb-1 d-flex align-items-start gap-2" style="color:#dcdcaa;"><span style="min-width:20px;">…</span><span style="min-width:200px;color:#569cd6;">Authentication</span><span style="color:#ce9178;">Requesting OAuth token...</span></div>\n')

        try:
            service = FNBStatementService()
        except Exception as e:
            yield from emit(f'<div class="mb-1 d-flex align-items-start gap-2" style="color:#f14c4c;"><span style="min-width:20px;">✗</span><span style="min-width:200px;color:#569cd6;">Auth Failed</span><span style="color:#ce9178;">{e}</span></div>\n')
            return

        yield from emit(f'<div class="mb-1 d-flex align-items-start gap-2" style="color:#4ec9b0;"><span style="min-width:20px;">✓</span><span style="min-width:200px;color:#569cd6;">Authentication</span><span style="color:#ce9178;">Token obtained successfully</span></div>\n')

        accounts_qs = FNBAccount.objects.filter(is_active=True, account_type='debtor')
        if account_number:
            accounts_qs = accounts_qs.filter(account_number=account_number)

        if not accounts_qs.exists():
            yield from emit(f'<div class="mb-1 d-flex align-items-start gap-2" style="color:#f14c4c;"><span style="min-width:20px;">✗</span><span style="min-width:200px;color:#569cd6;">No Accounts</span><span style="color:#ce9178;">No active debtor accounts found.</span></div>\n')
            return

        for account in accounts_qs:
            yield from emit(f'<div class="mb-1 d-flex align-items-start gap-2" style="color:#dcdcaa;"><span style="min-width:20px;">…</span><span style="min-width:200px;color:#569cd6;">Fetching {account.account_number}</span><span style="color:#ce9178;">Connecting to FNB...</span></div>\n')

            try:
                result = service.fetch_statement_range(account.account_number, statement_date)
                if opening_balance is None:
                    opening_balance = _format_balance(result["opening_balance"])
                    closing_balance = _format_balance(result["closing_balance"])

                yield from emit(f'<div class="mb-1 d-flex align-items-start gap-2" style="color:#4ec9b0;"><span style="min-width:20px;">✓</span><span style="min-width:200px;color:#569cd6;">Downloaded {account.account_number}</span><span style="color:#ce9178;">{len(result["entries"])} entries received</span></div>\n')

                txns = FNBStatementService.parse_entries(result["entries"])
                yield from emit(f'<div class="mb-1 d-flex align-items-start gap-2" style="color:#dcdcaa;"><span style="min-width:20px;">…</span><span style="min-width:200px;color:#569cd6;">Saving {account.account_number}</span><span style="color:#ce9178;">Processing {len(txns)} transactions...</span></div>\n')

                for txn in txns:
                    mapped_to = _check_mapped(txn)
                    obj, created = FNBTransaction.objects.get_or_create(
                        account=account,
                        transaction_date=txn["transaction_date"],
                        description=txn["description"],
                        debit_amount=txn["debit_amount"],
                        credit_amount=txn["credit_amount"],
                        defaults={
                            "reference": txn["reference"],
                            "balance": txn["balance"],
                            "transaction_type": txn["transaction_type"],
                            "mapped_to": mapped_to,
                        },
                    )
                    if not created and mapped_to and not obj.mapped_to:
                        obj.mapped_to = mapped_to
                        obj.save(update_fields=['mapped_to'])
                    all_fetched.append(obj)
                    if created:
                        total += 1

                yield from emit(f'<div class="mb-1 d-flex align-items-start gap-2" style="color:#4ec9b0;"><span style="min-width:20px;">✓</span><span style="min-width:200px;color:#569cd6;">Saved {account.account_number}</span><span style="color:#ce9178;">{total} new transactions stored</span></div>\n')

            except Exception as e:
                yield from emit(f'<div class="mb-1 d-flex align-items-start gap-2" style="color:#f14c4c;"><span style="min-width:20px;">✗</span><span style="min-width:200px;color:#569cd6;">Error {account.account_number}</span><span style="color:#ce9178;">{e}</span></div>\n')

        all_fetched.sort(key=lambda t: t.transaction_date)
        yield from emit(f'<div class="mb-1 d-flex align-items-start gap-2" style="color:#4ec9b0;"><span style="min-width:20px;">✓</span><span style="min-width:200px;color:#569cd6;">Complete</span><span style="color:#ce9178;">Synced {total} new transactions successfully</span></div>\n')

        import json
        from django.template.loader import render_to_string

        table_html = render_to_string('fnb/_statement_table.html', {
            'fetched_transactions': all_fetched,
            'opening_balance': opening_balance,
            'closing_balance': closing_balance,
        })

        done_data = json.dumps({"type": "done", "table": table_html})
        yield f"data: {done_data}\n\n"

    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response


def bank_payments(request):
    payments = FNBPaymentRecord.objects.select_related('debtor_account', 'creditor_account', 'initiated_by').order_by('-initiated_at')
    return render(request, 'fnb/bank_payments.html', {'payments': payments})


def bank_make_payment(request):
    log_steps = []

    if request.method == 'POST':
        creditor_id = request.POST.get('creditor_account')
        amount = Decimal(request.POST.get('amount', '0'))
        reference = request.POST.get('reference', '')
        expense_id = request.POST.get('expense_id', '')

        debtor = FNBAccount.objects.filter(account_type='debtor', is_active=True).first()
        creditor = get_object_or_404(FNBAccount, id=creditor_id)

        if not debtor:
            LOG_STEPS.clear()
            LOG_STEPS.append({"step": "Configuration Error", "status": "error", "icon": "✗", "detail": "No debtor account configured."})
            log_steps = list(LOG_STEPS)
            messages.error(request, "No debtor account configured. Run seed_fnb_accounts first.")
        elif amount <= 0:
            LOG_STEPS.clear()
            LOG_STEPS.append({"step": "Validation Error", "status": "error", "icon": "✗", "detail": "Amount must be greater than zero."})
            log_steps = list(LOG_STEPS)
            messages.error(request, "Amount must be greater than zero.")
        else:
            LOG_STEPS.clear()
            try:
                LOG_STEPS.append({"step": "Payment Initiation", "status": "pending", "icon": "…", "detail": f"Preparing R{amount} to {creditor.account_number}"})
                service = FNBPaymentService()
                response = service.create_payment(
                    debtor_account=debtor.account_number,
                    debtor_branch=debtor.branch_code,
                    creditor_account=creditor.account_number,
                    creditor_branch=creditor.branch_code,
                    amount=amount,
                    reference=reference[:20],
                    creditor_name=creditor.account_holder or "Beneficiary",
                )

                LOG_STEPS.append({"step": "Saving Record", "pending": "pending", "status": "pending", "icon": "…", "detail": "Saving payment record to database..."})
                record = FNBPaymentRecord.objects.create(
                    debtor_account=debtor,
                    creditor_account=creditor,
                    amount=amount,
                    reference=reference[:20],
                    description=request.POST.get('description', ''),
                    status='sent',
                    fnb_response=response,
                    initiated_by=request.user,
                )
                LOG_STEPS.append({"step": "Saving Record", "status": "ok", "icon": "✓", "detail": f"Payment record #{record.id} saved"})

                if expense_id:
                    expense = get_object_or_404(Expense, id=expense_id)
                    record.expense = expense
                    record.save()
                    expense.amount_paid += amount
                    expense.save()
                    LOG_STEPS.append({"step": "Update Expense", "status": "ok", "icon": "✓", "detail": f"Expense #{expense.id} updated (paid R{amount})"})

                LOG_STEPS.append({"step": "Complete", "status": "ok", "icon": "✓", "detail": f"Payment of R{amount} sent successfully"})
                log_steps = list(LOG_STEPS)
                messages.success(request, f"Payment of R{amount} sent to {creditor.account_number}")
            except Exception as e:
                LOG_STEPS.append({"step": "Payment Failed", "status": "error", "icon": "✗", "detail": str(e)})
                log_steps = list(LOG_STEPS)
                messages.error(request, f"Payment failed: {e}")

        creditors = FNBAccount.objects.filter(account_type='creditor', is_active=True)
        expense = Expense.objects.filter(id=expense_id).first() if expense_id else None
        return render(request, 'fnb/bank_payment_form.html', {
            'creditors': creditors,
            'expense': expense,
            'log_steps': log_steps,
        })

    creditors = FNBAccount.objects.filter(account_type='creditor', is_active=True)
    expense_id = request.GET.get('expense_id', '')
    expense = None
    if expense_id:
        expense = get_object_or_404(Expense, id=expense_id)

    return render(request, 'fnb/bank_payment_form.html', {
        'creditors': creditors,
        'expense': expense,
        'log_steps': log_steps,
    })
