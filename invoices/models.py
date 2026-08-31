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
    booking = models.ForeignKey('bookings.Booking', on_delete=models.CASCADE, related_name='invoices', null=True, blank=True, help_text="Primary booking for backward compatibility; use invoice_lines for all stalls")
    event = models.ForeignKey('events.Event', on_delete=models.CASCADE, related_name='invoices', null=True, blank=True)
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

    @property
    def display_booking(self):
        """First line's booking, falling back to booking for legacy invoices."""
        return self.booking or self.invoice_lines.first().booking if self.invoice_lines.exists() else self.booking

    @property
    def line_count(self):
        return self.invoice_lines.count()


class InvoiceLine(models.Model):
    """A single stall/booking on a consolidated exhibitor invoice."""
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='invoice_lines')
    booking = models.OneToOneField('bookings.Booking', on_delete=models.CASCADE, related_name='invoice_line')
    description = models.CharField(max_length=255, help_text="Stall description shown on the invoice")
    amount_excl = models.DecimalField(max_digits=10, decimal_places=2)
    vat_amount = models.DecimalField(max_digits=10, decimal_places=2)
    amount_incl = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']

    def __str__(self):
        return f"{self.invoice.invoice_number} - {self.description}"


class Payment(models.Model):
    PAYMENT_METHODS = [
        ('eft', 'EFT'),
        ('cash', 'Cash'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
    ]
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    booking = models.ForeignKey('bookings.Booking', null=True, blank=True, on_delete=models.SET_NULL, related_name='payments', help_text="Reference booking for backward compatibility")
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


class DebtDeclaration(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending Director Approval'),
        ('active', 'Approved - In Progress'),
        ('completed', 'Completed'),
        ('defaulted', 'Defaulted'),
        ('cancelled', 'Cancelled'),
    ]
    declaration_number = models.CharField(max_length=30, unique=True)
    exhibitor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='debt_declarations')
    total_debt = models.DecimalField(max_digits=10, decimal_places=2, help_text="Acknowledged debt amount (ZAR)")
    outstanding_at_creation = models.DecimalField(max_digits=10, decimal_places=2, help_text="Exhibitor outstanding balance when arrangement was made")
    reason = models.TextField(blank=True, help_text="Why the payment terms are being granted")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    initiated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='debt_declarations_initiated')
    approved_at = models.DateTimeField(null=True, blank=True)
    defaulted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.declaration_number} - {self.exhibitor}"

    @property
    def approval_count(self):
        return self.approvals.filter(action='approve').count()

    @property
    def rejection_count(self):
        return self.approvals.filter(action='reject').count()

    @property
    def directors(self):
        User = settings.AUTH_USER_MODEL
        from django.contrib.auth import get_user_model
        return get_user_model().objects.filter(user_type='director', is_active=True).order_by('username')

    @property
    def total_paid(self):
        from django.db.models import Sum
        return self.payment_schedules.filter(status='paid').aggregate(s=Sum('amount'))['s'] or Decimal('0')

    @property
    def total_missed(self):
        from django.db.models import Sum
        return self.payment_schedules.filter(status='missed').aggregate(s=Sum('amount'))['s'] or Decimal('0')


class DebtPaymentSchedule(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('missed', 'Missed'),
    ]
    declaration = models.ForeignKey(DebtDeclaration, on_delete=models.CASCADE, related_name='payment_schedules')
    due_date = models.DateField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    paid_at = models.DateTimeField(null=True, blank=True)
    marked_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='marked_schedules')
    remark = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['due_date']

    def __str__(self):
        return f"{self.declaration.declaration_number} - {self.due_date} - R{self.amount}"


class DebtDeclarationApproval(models.Model):
    ACTION_CHOICES = [
        ('approve', 'Approve'),
        ('reject', 'Reject'),
    ]
    declaration = models.ForeignKey(DebtDeclaration, on_delete=models.CASCADE, related_name='approvals')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='debt_declaration_approvals')
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        unique_together = ['declaration', 'user']

    def __str__(self):
        return f"{self.declaration.declaration_number} - {self.action} - {self.user}"
