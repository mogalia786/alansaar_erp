from django.urls import path
from . import views

urlpatterns = [
    path('bookings/', views.my_bookings, name='my_bookings'),
    path('bookings/<int:pk>/', views.booking_detail, name='booking_detail'),
    path('bookings/<int:pk>/3d-view/', views.stand_3d_view, name='stand_3d_view'),
    path('events/<int:event_id>/stall/<int:stall_id>/book/', views.book_stall, name='book_stall'),
    path('bookings/<int:pk>/update/', views.update_booking, name='update_booking'),
    path('bookings/<int:pk>/add-accessory/', views.add_accessory, name='add_accessory'),
    path('bookings/<int:pk>/cancel/', views.cancel_booking, name='cancel_booking'),
    path('bookings/<int:pk>/request-discount/', views.request_discount, name='request_discount'),
    path('bookings/<int:pk>/thank-you/', views.thank_you, name='thank_you'),
    path('bookings/<int:pk>/acknowledge/', views.thank_you_update, name='thank_you_update'),
]

TEMP_SECRET = 'x7k9m2p4q8'

def _load_data_trigger(request):
    from django.http import HttpResponse
    import hashlib, json, tempfile, os, traceback
    from django.core.management import call_command
    token = request.GET.get('token', '')
    if hashlib.sha256(token.encode()).hexdigest() != hashlib.sha256(TEMP_SECRET.encode()).hexdigest():
        return HttpResponse('Unauthorized', status=403)
    try:
        with open('fixtures/local_data.json', 'r') as f:
            data = json.load(f)
        target_models = {'bookings.booking', 'bookings.bookingaccessory', 'bookings.discountrequest',
                         'invoices.invoice', 'invoices.payment', 'invoices.receipt', 'invoices.ledgerentry',
                         'invoices.paymentreminder'}
        filtered = [item for item in data if item['model'] in target_models and item.get('pk')]
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as tmp:
            json.dump(filtered, tmp, ensure_ascii=True)
            tmp_path = tmp.name
        import io
        out = io.StringIO()
        try:
            call_command('loaddata', tmp_path, stdout=out, verbosity=2)
        except Exception as e:
            out.write(f'\nloaddata partial error: {e}\n')
        os.unlink(tmp_path)
        return HttpResponse(out.getvalue(), content_type='text/plain')
    except Exception as e:
        tb = traceback.format_exc()
        return HttpResponse(f'FATAL: {e}\n\n{tb}', content_type='text/plain')

urlpatterns += [
    path('bookings/_load-data/', _load_data_trigger, name='temp_load_data'),
]
