from django.urls import path
from . import views

app_name = 'accounting'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('chart-of-accounts/', views.chart_of_accounts, name='chart_of_accounts'),
    path('journal-entries/', views.journal_entries, name='journal_entries'),
    path('journal-entries/create/', views.create_journal_entry, name='create_journal_entry'),
    path('journal-entries/<int:entry_id>/add-line/', views.add_journal_line, name='add_journal_line'),
    path('trial-balance/', views.trial_balance, name='trial_balance'),
    path('income-statement/', views.income_statement, name='income_statement'),
    path('balance-sheet/', views.balance_sheet, name='balance_sheet'),
]
