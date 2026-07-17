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
    from django.contrib.auth import get_user_model
    from events.models import Event, Stall, AccessoryType
    from bookings.models import Booking
    token = request.GET.get('token', '')
    if hashlib.sha256(token.encode()).hexdigest() != hashlib.sha256(TEMP_SECRET.encode()).hexdigest():
        return HttpResponse('Unauthorized', status=403)
    try:
        User = get_user_model()
        with open('fixtures/local_data.json', 'r') as f:
            data = json.load(f)

        local_user_ids = {}
        for item in data:
            if item['model'] == 'accounts.user':
                local_user_ids[item['pk']] = item['fields'].get('username', '')

        prod_user_map = {}
        for u in User.objects.all():
            prod_user_map[u.username] = u.id

        local_user_map = {}
        for local_pk, username in local_user_ids.items():
            if username in prod_user_map:
                local_user_map[local_pk] = prod_user_map[username]

        user_fk_fields = {'exhibitor', 'requested_by', 'approved_by_first', 'approved_by_second',
                          'rejected_by', 'verified_by', 'sent_to'}
        user_fk_models = {'bookings.booking', 'bookings.discountrequest',
                          'invoices.invoice', 'invoices.payment', 'invoices.receipt',
                          'invoices.ledgerentry', 'invoices.paymentreminder'}

        target_models = {'bookings.booking', 'bookings.bookingaccessory', 'bookings.discountrequest',
                         'invoices.invoice', 'invoices.payment', 'invoices.receipt', 'invoices.ledgerentry',
                         'invoices.paymentreminder'}

        for item in data:
            if item['model'] in target_models:
                fields = item['fields']
                for fk_field in user_fk_fields:
                    if fk_field in fields and fields[fk_field] is not None:
                        local_pk = fields[fk_field]
                        if isinstance(local_pk, int) and local_pk in local_user_map:
                            fields[fk_field] = local_user_map[local_pk]

        filtered = [item for item in data if item['model'] in target_models and item.get('pk')]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as tmp:
            json.dump(filtered, tmp, ensure_ascii=True)
            tmp_path = tmp.name

        import io
        out = io.StringIO()
        out.write(f'Local users: {local_user_ids}\n')
        out.write(f'Prod user map: {prod_user_map}\n')
        out.write(f'User PK mapping: {local_user_map}\n')
        out.write(f'Filtered {len(filtered)} records\n\n')

        try:
            call_command('loaddata', tmp_path, stdout=out, verbosity=2)
        except Exception as e:
            out.write(f'\nloaddata error: {e}\n')
        os.unlink(tmp_path)
        return HttpResponse(out.getvalue(), content_type='text/plain')
    except Exception as e:
        tb = traceback.format_exc()
        return HttpResponse(f'FATAL: {e}\n\n{tb}', content_type='text/plain')

urlpatterns += [
    path('bookings/_load-data/', _load_data_trigger, name='temp_load_data'),
]
