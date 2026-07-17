from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.conf import settings
from django.utils import timezone
from decimal import Decimal
from .models import RFQ, Quotation, QuotationDocument


def public_rfq_list(request):
    rfqs_open = RFQ.objects.filter(status='open', closing_date__gte=timezone.now()).order_by('closing_date')
    rfqs_closed = RFQ.objects.filter(status__in=['closed', 'awarded']).order_by('-closing_date')[:10]
    return render(request, 'rfq/public_list.html', {
        'rfqs_open': rfqs_open,
        'rfqs_closed': rfqs_closed,
    })


def public_rfq_detail(request, rfq_id):
    rfq = get_object_or_404(
        RFQ.objects.select_related('category'),
        pk=rfq_id,
        status__in=['open', 'closed', 'awarded'],
    )
    return render(request, 'rfq/public_detail.html', {
        'rfq': rfq,
    })


def public_submit_quotation(request, rfq_id):
    rfq = get_object_or_404(RFQ, pk=rfq_id, status='open')
    if timezone.now() > rfq.closing_date:
        messages.error(request, 'The closing date for this RFQ has passed.')
        return redirect('rfq_detail', rfq_id=rfq_id)
    if request.method == 'POST':
        excl = Decimal(request.POST.get('total_amount_excl', '0'))
        vat = excl * Decimal('0.15')
        incl = excl + vat
        quotation = Quotation.objects.create(
            rfq=rfq,
            provider=None,
            submitter_company_name=request.POST.get('company_name', ''),
            submitter_email=request.POST.get('email', ''),
            submitter_phone=request.POST.get('phone', ''),
            submitter_contact_person=request.POST.get('contact_person', ''),
            submitter_registration_number=request.POST.get('registration_number', ''),
            submitter_vat_number=request.POST.get('vat_number', ''),
            submitter_company_type=request.POST.get('company_type', ''),
            cover_letter=request.POST.get('cover_letter', ''),
            methodology=request.POST.get('methodology', ''),
            total_amount_excl=excl,
            vat_amount=vat,
            total_amount_incl=incl,
            payment_terms=request.POST.get('payment_terms', ''),
            validity_period=request.POST.get('validity_period', ''),
            delivery_timeline=request.POST.get('delivery_timeline', ''),
            status='submitted',
            submitted_by_provider=False,
        )
        files = request.FILES.getlist('documents')
        for f in files:
            QuotationDocument.objects.create(
                quotation=quotation,
                document=f,
                filename=f.name,
                file_size=f.size,
            )
        try:
            from notifications.utils import send_quotation_submitted
            send_quotation_submitted(quotation)
        except Exception:
            pass
        messages.success(
            request,
            'Your quotation has been submitted successfully. '
            'You will be notified via email regarding the outcome.'
        )
        return redirect('rfq_detail', rfq_id=rfq_id)
    return render(request, 'rfq/submit_quotation.html', {
        'rfq': rfq,
    })
