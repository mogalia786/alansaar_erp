from django.http import HttpResponse
from django.utils import timezone
from providers.models import RFQ


def fix_reopen_rfqs(request):
    fixed = []
    for rfq in RFQ.objects.filter(status='closed'):
        if rfq.closing_date and rfq.closing_date > timezone.now():
            rfq.status = 'open'
            rfq.save()
            fixed.append(rfq.rfq_number)
    return HttpResponse(f'Re-opened: {fixed}' if fixed else 'No RFQs needed reopening')
