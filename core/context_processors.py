from django.conf import settings

def site_config(request):
    return {
        'site_name': settings.SITE_NAME,
        'currency_symbol': settings.CURRENCY_SYMBOL,
        'vat_rate': settings.VAT_RATE,
        'MEDIA_URL': settings.MEDIA_URL,
    }
