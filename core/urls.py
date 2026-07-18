from django.contrib import admin
from django.http import HttpResponse, Http404, FileResponse
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from providers import rfq_views
from core.views import fix_reopen_rfqs
import os

def health_check(request):
    return HttpResponse("OK", status=200)

def serve_media(request, path):
    full_path = os.path.join(str(settings.MEDIA_ROOT), path)
    full_path = os.path.normpath(full_path)
    if not full_path.startswith(str(settings.MEDIA_ROOT)):
        raise Http404
    if not os.path.isfile(full_path):
        raise Http404
    return FileResponse(open(full_path, 'rb'))

urlpatterns = [
    path('healthz/', health_check),
    path('_fix/reopen-rfqs/', fix_reopen_rfqs),
    path('media/<path:path>', serve_media, name='serve_media'),
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
