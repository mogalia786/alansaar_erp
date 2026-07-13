from django.db import models
from django.conf import settings
from decimal import Decimal


class Account(models.Model):
    ACCOUNT_TYPES = [
        ('asset', 'Asset'),
        ('liability', 'Liability'),
        ('equity', 'Equity'),
        ('income', 'Income'),
        ('expense', 'Expense'),
    ]
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    type = models.CharField(max_length=20, choices=ACCOUNT_TYPES)
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"

    def balance(self):
        debits = self.lines.aggregate(models.Sum('debit'))['debit__sum'] or Decimal('0')
        credits = self.lines.aggregate(models.Sum('credit'))['credit__sum'] or Decimal('0')
        if self.type in ['asset', 'expense']:
            return debits - credits
        return credits - debits


class JournalEntry(models.Model):
    entry_number = models.CharField(max_length=30, unique=True)
    date = models.DateField()
    description = models.TextField()
    is_posted = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='journal_entries',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name_plural = 'Journal entries'

    def __str__(self):
        return f"{self.entry_number} - {self.date}"

    @property
    def total_debit(self):
        return self.lines.aggregate(models.Sum('debit'))['debit__sum'] or Decimal('0')

    @property
    def total_credit(self):
        return self.lines.aggregate(models.Sum('credit'))['credit__sum'] or Decimal('0')

    def is_balanced(self):
        return self.total_debit == self.total_credit


class JournalLine(models.Model):
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name='lines')
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='lines')
    description = models.CharField(max_length=255, blank=True)
    debit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.account.code} D{self.debit} C{self.credit}"
