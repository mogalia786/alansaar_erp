from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.exhibitor_login, name='login'),
    path('register/', views.exhibitor_register, name='register'),
    path('check-username/', views.check_username, name='check_username'),
    path('forgot-password/', views.forgot_password, name='forgot_password'),
    path('change-password/', views.change_password, name='change_password'),
    path('logout/', views.exhibitor_logout, name='logout'),
    path('dashboard/', views.exhibitor_dashboard, name='dashboard'),
    path('notifications/', views.notifications_view, name='notifications'),
]
