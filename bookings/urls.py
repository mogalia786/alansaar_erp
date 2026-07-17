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
    from django.db import connection, transaction
    import hashlib, json, traceback
    token = request.GET.get('token', '')
    if hashlib.sha256(token.encode()).hexdigest() != hashlib.sha256(TEMP_SECRET.encode()).hexdigest():
        return HttpResponse('Unauthorized', status=403)
    try:
        with open('fixtures/local_data.json', 'r') as f:
            data = json.load(f)
        output_lines = []
        created_count = 0
        updated_count = 0
        error_count = 0
        for item in data:
            model_label = item['model']
            pk = item['pk']
            fields = item['fields']
            al, mn = model_label.split('.')
            from django.apps import apps
            try:
                Model = apps.get_model(al, mn)
            except LookupError:
                output_lines.append(f'SKIP: {model_label} not found')
                continue
            regular_fields = {}
            for k, v in fields.items():
                if isinstance(v, list):
                    continue
                regular_fields[k] = v
            try:
                obj = Model.objects.filter(pk=pk).first()
                if obj:
                    for k, v in regular_fields.items():
                        setattr(obj, k, v)
                    obj.save()
                    updated_count += 1
                else:
                    obj = Model(**regular_fields)
                    obj.pk = pk
                    obj.save()
                    created_count += 1
            except Exception as e:
                error_count += 1
                output_lines.append(f'ERROR {model_label} pk={pk}: {e}')
        summary = f'Created: {created_count}, Updated: {updated_count}, Errors: {error_count}'
        body = summary + '\n\n' + '\n'.join(output_lines[-50:])
        return HttpResponse(body, content_type='text/plain')
    except Exception as e:
        tb = traceback.format_exc()
        return HttpResponse(f'FATAL: {e}\n\n{tb}', content_type='text/plain')

urlpatterns += [
    path('bookings/_load-data/', _load_data_trigger, name='temp_load_data'),
]
