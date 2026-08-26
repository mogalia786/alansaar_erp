from django.conf import settings

def site_config(request):
    ctx = {
        'site_name': settings.SITE_NAME,
        'currency_symbol': settings.CURRENCY_SYMBOL,
        'vat_rate': settings.VAT_RATE,
        'MEDIA_URL': settings.MEDIA_URL,
    }
    if request.user.is_authenticated and hasattr(request.user, 'has_erp_permission'):
        from accounts.models import User
        ctx['pending_count'] = User.objects.filter(user_type='exhibitor', is_verified=False, is_active=True).count()
    return ctx
