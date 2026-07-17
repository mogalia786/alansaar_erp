from django.urls import path
from . import views

urlpatterns = [
    path('invoices/', views.my_invoices, name='my_invoices'),
    path('invoices/<int:pk>/', views.invoice_detail, name='invoice_detail'),
    path('invoices/<int:pk>/pay/', views.make_payment, name='make_payment'),
    path('invoices/<int:pk>/print/', views.print_invoice, name='print_invoice'),
    path('invoices/<int:pk>/receipt/', views.print_receipt, name='print_receipt'),
    path('invoices/<int:pk>/payments-receipt/', views.print_payments_receipt, name='print_payments_receipt'),
    path('statement/', views.account_statement, name='account_statement'),
]
