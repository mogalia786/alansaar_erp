from django.urls import path
from . import views

app_name = 'providers'

urlpatterns = [
    path('login/', views.provider_login, name='login'),
    path('logout/', views.provider_logout, name='logout'),
    path('change-password/', views.provider_change_password, name='change_password'),
    path('', views.provider_dashboard, name='dashboard'),
    path('events/', views.provider_events, name='events'),
    path('events/<int:event_id>/', views.provider_event_detail, name='event_detail'),
    path('my-quotations/', views.provider_my_quotations, name='my_quotations'),
]
