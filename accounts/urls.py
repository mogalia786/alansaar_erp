from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.exhibitor_login, name='login'),
    path('register/', views.exhibitor_register, name='register'),
    path('logout/', views.exhibitor_logout, name='logout'),
    path('dashboard/', views.exhibitor_dashboard, name='dashboard'),
    path('notifications/', views.notifications_view, name='notifications'),
]
