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
