from django.contrib import admin
from .models import FNBAccessToken, FNBAccount, FNBTransaction, FNBPaymentRecord


@admin.register(FNBAccessToken)
class FNBAccessTokenAdmin(admin.ModelAdmin):
    list_display = ['id', 'expires_at', 'created_at']
    readonly_fields = ['token', 'expires_at', 'created_at']


@admin.register(FNBAccount)
class FNBAccountAdmin(admin.ModelAdmin):
    list_display = ['account_number', 'branch_code', 'account_type', 'account_holder', 'is_active']
    list_filter = ['account_type', 'is_active']
    search_fields = ['account_number', 'account_holder']


@admin.register(FNBTransaction)
class FNBTransactionAdmin(admin.ModelAdmin):
    list_display = ['account', 'transaction_date', 'description', 'debit_amount', 'credit_amount', 'balance']
    list_filter = ['account', 'transaction_type']
    search_fields = ['description', 'reference']
    date_hierarchy = 'transaction_date'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('account')


@admin.register(FNBPaymentRecord)
class FNBPaymentRecordAdmin(admin.ModelAdmin):
    list_display = ['id', 'debtor_account', 'creditor_account', 'amount', 'reference', 'status', 'initiated_at']
    list_filter = ['status']
    search_fields = ['reference', 'debtor_account__account_number', 'creditor_account__account_number']
