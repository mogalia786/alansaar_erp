from django.db import models
from django.conf import settings
from decimal import Decimal


class Invoice(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('partial', 'Partially Paid'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled'),
    ]
    invoice_number = models.CharField(max_length=30, unique=True)
    booking = models.ForeignKey('bookings.Booking', on_delete=models.CASCADE, related_name='invoices')
    exhibitor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='invoices')
    amount_excl = models.DecimalField(max_digits=10, decimal_places=2)
    vat_amount = models.DecimalField(max_digits=10, decimal_places=2)
    amount_incl = models.DecimalField(max_digits=10, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    balance_due = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    issue_date = models.DateField()
    due_date = models.DateField()
    paid_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    pdf_file = models.FileField(upload_to='invoices/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-issue_date']

    def __str__(self):
        return self.invoice_number


class Payment(models.Model):
    PAYMENT_METHODS = [
        ('eft', 'EFT'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
    ]
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    booking = models.ForeignKey('bookings.Booking', on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='eft')
    reference_number = models.CharField(max_length=100, blank=True)
    proof_of_payment = models.FileField(upload_to='proof_of_payment/', blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='verified_payments')
    verified_at = models.DateTimeField(null=True, blank=True)
    payment_date = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)
    receipt_number = models.CharField(max_length=30, blank=True)

    class Meta:
        ordering = ['-payment_date']

    def __str__(self):
        return f"Payment {self.id} - {self.amount}"


class PaymentReminder(models.Model):
    booking = models.ForeignKey('bookings.Booking', on_delete=models.CASCADE, related_name='payment_reminders')
    sent_at = models.DateTimeField(auto_now_add=True)
    sent_to = models.EmailField()
    reminder_type = models.CharField(max_length=20, default='overdue')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-sent_at']


class LedgerEntry(models.Model):
    ENTRY_TYPES = [
        ('invoice', 'Invoice'),
        ('payment', 'Payment'),
        ('credit', 'Credit Note'),
        ('debit', 'Debit Note'),
    ]
    exhibitor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ledger_entries')
    booking = models.ForeignKey('bookings.Booking', on_delete=models.CASCADE, related_name='ledger_entries')
    entry_type = models.CharField(max_length=20, choices=ENTRY_TYPES)
    description = models.CharField(max_length=255)
    reference = models.CharField(max_length=50, blank=True)
    debit = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Amount owed (invoice)")
    credit = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Amount paid (payment)")
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    entry_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['entry_date', 'created_at']
        verbose_name_plural = 'Ledger entries'

    def __str__(self):
        return f"{self.get_entry_type_display()} - {self.reference} - R{self.debit|self.credit}"


class Receipt(models.Model):
    receipt_number = models.CharField(max_length=30, unique=True)
    payment = models.OneToOneField(Payment, on_delete=models.CASCADE, related_name='receipt')
    exhibitor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='receipts')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20)
    reference_number = models.CharField(max_length=100, blank=True)
    issue_date = models.DateField()
    notes = models.TextField(blank=True)
    pdf_file = models.FileField(upload_to='receipts/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-issue_date']

    def __str__(self):
        return self.receipt_number
