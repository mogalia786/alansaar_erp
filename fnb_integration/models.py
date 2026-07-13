from django.db import models
from django.conf import settings
from decimal import Decimal


class FNBAccessToken(models.Model):
    token = models.TextField()
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "FNB Access Token"
        verbose_name_plural = "FNB Access Tokens"
        ordering = ['-created_at']

    def __str__(self):
        return f"Token expires {self.expires_at.strftime('%Y-%m-%d %H:%M')}"


class FNBAccount(models.Model):
    ACCOUNT_TYPES = [
        ('debtor', 'Business Account (Debtor)'),
        ('creditor', 'Beneficiary Account (Creditor)'),
    ]
    account_number = models.CharField(max_length=20, unique=True)
    branch_code = models.CharField(max_length=10, default='250655')
    bic = models.CharField(max_length=11, default='FIRNZAJJ')
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES)
    account_holder = models.CharField(max_length=200, blank=True)
    description = models.CharField(max_length=200, blank=True, help_text="Internal label")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['account_type', 'account_number']

    def __str__(self):
        return f"{self.account_number} ({self.get_account_type_display()})"


class FNBTransaction(models.Model):
    account = models.ForeignKey(FNBAccount, on_delete=models.CASCADE, related_name='transactions')
    transaction_id = models.CharField(max_length=100, blank=True)
    transaction_date = models.DateTimeField()
    description = models.TextField(blank=True)
    reference = models.CharField(max_length=100, blank=True)
    debit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    credit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    balance = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    transaction_type = models.CharField(max_length=20, blank=True)
    mapped_to = models.CharField(max_length=200, blank=True, null=True, help_text="Auto-mapped invoice/expense reference")
    raw_data = models.JSONField(blank=True, null=True)
    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-transaction_date']
        unique_together = ['account', 'transaction_date', 'description', 'debit_amount', 'credit_amount']
        verbose_name = "FNB Transaction"
        verbose_name_plural = "FNB Transactions"

    def __str__(self):
        return f"{self.transaction_date.strftime('%Y-%m-%d')} R{self.debit_amount or self.credit_amount} {self.description[:40]}"


class FNBPaymentRecord(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent to FNB'),
        ('confirmed', 'Confirmed'),
        ('failed', 'Failed'),
        ('reversed', 'Reversed'),
    ]
    debtor_account = models.ForeignKey(FNBAccount, on_delete=models.CASCADE, related_name='outgoing_payments')
    creditor_account = models.ForeignKey(FNBAccount, on_delete=models.CASCADE, related_name='incoming_payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reference = models.CharField(max_length=100, blank=True)
    description = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    fnb_response = models.JSONField(blank=True, null=True)
    fnb_request_id = models.CharField(max_length=100, blank=True)
    expense = models.ForeignKey('providers.Expense', on_delete=models.SET_NULL, null=True, blank=True, related_name='fnb_payments')
    invoice = models.ForeignKey('invoices.Invoice', on_delete=models.SET_NULL, null=True, blank=True, related_name='fnb_payments')
    initiated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='fnb_payments')
    initiated_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-initiated_at']
        verbose_name = "FNB Payment Record"
        verbose_name_plural = "FNB Payment Records"

    def __str__(self):
        return f"R{self.amount} to {self.creditor_account.account_number} ({self.status})"
