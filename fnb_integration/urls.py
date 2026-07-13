from django.urls import path
from . import views

app_name = 'fnb'

urlpatterns = [
    path('', views.bank_dashboard, name='dashboard'),
    path('transactions/', views.bank_transactions, name='transactions'),
    path('sync/', views.bank_sync_statements, name='sync'),
    path('payments/', views.bank_payments, name='payments'),
    path('payments/create/', views.bank_make_payment, name='make_payment'),
]
