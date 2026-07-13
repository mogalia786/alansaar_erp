from django.contrib import admin
from django.http import HttpResponse
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from providers import rfq_views

def health_check(request):
    return HttpResponse("OK", status=200)

urlpatterns = [
    path('healthz/', health_check),
    path('admin/', admin.site.urls),
    path('erp/', include('portal.urls')),
    path('', include('accounts.urls')),
    path('', include('events.urls')),
    path('', include('bookings.urls')),
    path('', include('invoices.urls')),
    path('accounting/', include('accounting.urls')),
    path('providers/', include('providers.urls')),
    path('rfqs/', rfq_views.public_rfq_list, name='rfq_list'),
    path('rfqs/<int:rfq_id>/', rfq_views.public_rfq_detail, name='rfq_detail'),
    path('rfqs/<int:rfq_id>/submit/', rfq_views.public_submit_quotation, name='submit_quotation'),
    path('erp/banking/', include('fnb_integration.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
