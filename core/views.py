from django.http import HttpResponse
from providers.models import Quotation


def fix_unlink_quotations(request):
    fixed = []
    for q in Quotation.objects.filter(provider__isnull=False):
        # If the provider's email doesn't match the submitter's email, unlink
        if q.provider and q.submitter_email and q.provider.email.lower() != q.submitter_email.lower():
            old_provider = q.provider.company_name
            q.provider = None
            q.save()
            fixed.append(f'{q.quotation_number} (unlinked from {old_provider})')
    return HttpResponse(f'Fixed: {fixed}' if fixed else 'Nothing to fix')
