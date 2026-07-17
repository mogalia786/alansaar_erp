from django.db import models
from django.conf import settings
from decimal import Decimal
from django.contrib.auth.hashers import make_password, check_password


class ServiceProvider(models.Model):
    COMPANY_TYPES = [
        ('sole', 'Sole Proprietor'),
        ('ptyltd', 'PTY LTD'),
        ('cc', 'Close Corporation'),
        ('other', 'Other'),
    ]
    SERVICE_TYPES = [
        ('catering', 'Catering'),
        ('security', 'Security'),
        ('cleaning', 'Cleaning'),
        ('stand_builder', 'Stand Builder'),
        ('electrical', 'Electrical'),
        ('audio_visual', 'Audio/Visual'),
        ('logistics', 'Logistics'),
        ('other', 'Other'),
    ]
    ACCOUNT_TYPES = [
        ('cheque', 'Cheque Account'),
        ('savings', 'Savings Account'),
        ('current', 'Current Account'),
        ('business', 'Business Account'),
    ]
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=128)
    company_name = models.CharField(max_length=200)
    company_type = models.CharField(max_length=20, choices=COMPANY_TYPES, default='ptyltd')
    registration_number = models.CharField(max_length=50, blank=True)
    vat_number = models.CharField(max_length=20, blank=True)
    service_type = models.CharField(max_length=30, choices=SERVICE_TYPES, default='other')
    phone = models.CharField(max_length=20)
    alternative_phone = models.CharField(max_length=20, blank=True)
    contact_person = models.CharField(max_length=200, blank=True)
    physical_address = models.TextField(blank=True)
    postal_address = models.TextField(blank=True)
    bank_name = models.CharField(max_length=100, blank=True)
    bank_branch = models.CharField(max_length=100, blank=True)
    bank_account_number = models.CharField(max_length=30, blank=True)
    bank_account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES, default='business')
    bank_branch_code = models.CharField(max_length=20, blank=True)
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    must_change_password = models.BooleanField(default=False, help_text="Force password change on next login")
    created_at = models.DateTimeField(auto_now_add=True)

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)

    def save(self, *args, **kwargs):
        if self.password and not self.password.startswith('pbkdf2_'):
            self.password = make_password(self.password)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.company_name


class ServiceLog(models.Model):
    provider = models.ForeignKey(ServiceProvider, on_delete=models.CASCADE, related_name='service_logs')
    event = models.ForeignKey('events.Event', on_delete=models.SET_NULL, null=True, blank=True, related_name='service_logs')
    description = models.TextField()
    service_date = models.DateField()
    amount_charged = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-service_date']

    def __str__(self):
        return f"{self.provider.company_name} - {self.service_date}"


class Expense(models.Model):
    STATUS_CHOICES = [
        ('unpaid', 'Unpaid'),
        ('paid', 'Paid'),
        ('partial', 'Partially Paid'),
        ('cancelled', 'Cancelled'),
    ]
    CATEGORY_CHOICES = [
        ('stand_building', 'Stand Building'),
        ('electrical', 'Electrical'),
        ('cleaning', 'Cleaning'),
        ('security', 'Security'),
        ('catering', 'Catering'),
        ('audio_visual', 'Audio/Visual'),
        ('logistics', 'Logistics'),
        ('printing', 'Printing & Signage'),
        ('marketing', 'Marketing & Advertising'),
        ('admin', 'Administrative'),
        ('other', 'Other'),
    ]
    provider = models.ForeignKey(ServiceProvider, on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses')
    description = models.CharField(max_length=300)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default='other')
    amount_excl = models.DecimalField(max_digits=10, decimal_places=2)
    vat_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    amount_incl = models.DecimalField(max_digits=10, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    balance_due = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='unpaid')
    expense_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    paid_date = models.DateField(null=True, blank=True)
    payment_reference = models.CharField(max_length=100, blank=True)
    invoice_file = models.FileField(upload_to='expense_invoices/', blank=True, null=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='created_expenses')

    class Meta:
        ordering = ['-expense_date']

    def __str__(self):
        return f"{self.description[:50]} - R{self.amount_incl}"

    def save(self, *args, **kwargs):
        if not self.amount_incl and self.amount_excl:
            self.vat_amount = self.amount_excl * Decimal('0.15')
            self.amount_incl = self.amount_excl + self.vat_amount
        self.balance_due = self.amount_incl - self.amount_paid
        if self.balance_due <= 0 and self.amount_incl > 0:
            self.status = 'paid'
        elif self.amount_paid > 0:
            self.status = 'partial'
        super().save(*args, **kwargs)


class ServiceQuotation(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    quotation_number = models.CharField(max_length=20, unique=True)
    provider = models.ForeignKey(ServiceProvider, on_delete=models.CASCADE, related_name='quotations')
    event = models.ForeignKey('events.Event', on_delete=models.CASCADE, related_name='service_quotations')
    title = models.CharField(max_length=200)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.quotation_number} - {self.provider.company_name}"


class RFQCategory(models.Model):
    """International standard service categories for procurement (UNSPSC-aligned)."""
    code = models.CharField(max_length=20, unique=True, help_text="Category code (e.g., 72140000)")
    name = models.CharField(max_length=200, help_text="Category name")
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "RFQ Category"
        verbose_name_plural = "RFQ Categories"
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"


class RFQ(models.Model):
    """Request for Proposals / Request for Quotation."""
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('open', 'Open for Submissions'),
        ('closed', 'Closed'),
        ('awarded', 'Awarded'),
        ('cancelled', 'Cancelled'),
    ]
    rfq_number = models.CharField(max_length=30, unique=True)
    event = models.ForeignKey('events.Event', on_delete=models.SET_NULL, null=True, blank=True, related_name='rfqs')
    category = models.ForeignKey(RFQCategory, on_delete=models.SET_NULL, null=True, related_name='rfqs')
    title = models.CharField(max_length=300)
    description = models.TextField(help_text="Detailed scope of work / requirements")
    deliverables = models.TextField(blank=True, help_text="Expected deliverables / outputs")
    terms_and_conditions = models.TextField(blank=True, help_text="Procurement terms, conditions, and evaluation criteria")
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='normal')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    issue_date = models.DateField(null=True, blank=True)
    closing_date = models.DateTimeField(help_text="Deadline for proposal submissions")
    estimated_budget = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="Estimated budget range")
    contact_person = models.CharField(max_length=200, blank=True, help_text="Procurement contact")
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    site_visit_required = models.BooleanField(default=False)
    site_visit_date = models.DateTimeField(null=True, blank=True)
    documents = models.FileField(upload_to='rfq_documents/', blank=True, null=True, help_text="Supporting documents / terms of reference")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_rfqs')
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Request for Proposal"
        verbose_name_plural = "Requests for Proposals"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.rfq_number} - {self.title[:60]}"

    def save(self, *args, **kwargs):
        if not self.rfq_number:
            import uuid
            from django.utils import timezone
            year = timezone.now().strftime('%Y')
            short_id = uuid.uuid4().hex[:6].upper()
            self.rfq_number = f"RFP-{year}-{short_id}"
        super().save(*args, **kwargs)


class Quotation(models.Model):
    """Submitted proposal/quote in response to an RFQ."""
    STATUS_CHOICES = [
        ('submitted', 'Submitted'),
        ('shortlisted', 'Shortlisted'),
        ('acceptable', 'Accepted Pending Approval'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('withdrawn', 'Withdrawn'),
    ]
    quotation_number = models.CharField(max_length=30, unique=True)
    rfq = models.ForeignKey(RFQ, on_delete=models.CASCADE, related_name='quotations')
    provider = models.ForeignKey(ServiceProvider, on_delete=models.SET_NULL, null=True, blank=True, related_name='rfq_quotations')
    # Anonymous submitter info (used when provider is not logged in / not yet registered)
    submitter_company_name = models.CharField(max_length=200, blank=True)
    submitter_email = models.EmailField(max_length=200, blank=True)
    submitter_phone = models.CharField(max_length=20, blank=True)
    submitter_contact_person = models.CharField(max_length=200, blank=True)
    submitter_registration_number = models.CharField(max_length=50, blank=True)
    submitter_vat_number = models.CharField(max_length=20, blank=True)
    submitter_company_type = models.CharField(max_length=20, blank=True)
    cover_letter = models.TextField(blank=True, help_text="Cover letter / executive summary")
    methodology = models.TextField(blank=True, help_text="Technical approach and methodology")
    total_amount_excl = models.DecimalField(max_digits=12, decimal_places=2, help_text="Total quoted amount (excl VAT)")
    vat_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount_incl = models.DecimalField(max_digits=12, decimal_places=2, help_text="Total quoted amount (incl VAT)")
    payment_terms = models.CharField(max_length=200, blank=True, help_text="Proposed payment terms")
    validity_period = models.CharField(max_length=100, blank=True, help_text="Validity of quotation (e.g., 30 days)")
    delivery_timeline = models.CharField(max_length=200, blank=True, help_text="Proposed delivery / completion timeline")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='submitted')
    internal_notes = models.TextField(blank=True, help_text="ERP internal evaluation notes")
    submitted_by_provider = models.BooleanField(default=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    site_meeting_date = models.DateTimeField(null=True, blank=True, help_text="Scheduled site meeting date/time")

    class Meta:
        ordering = ['rfq', '-submitted_at']

    def __str__(self):
        name = self.provider.company_name if self.provider else self.submitter_company_name
        return f"{self.quotation_number} - {name}"

    def save(self, *args, **kwargs):
        if not self.quotation_number:
            import uuid
            from django.utils import timezone
            year = timezone.now().strftime('%Y')
            short_id = uuid.uuid4().hex[:6].upper()
            self.quotation_number = f"QTN-{year}-{short_id}"
        if self.total_amount_excl and not self.total_amount_incl:
            self.vat_amount = self.total_amount_excl * Decimal('0.15')
            self.total_amount_incl = self.total_amount_excl + self.vat_amount
        if self.total_amount_excl and not self.vat_amount:
            self.vat_amount = self.total_amount_excl * Decimal('0.15')
        super().save(*args, **kwargs)


class QuotationDocument(models.Model):
    """Uploaded documents attached to a quotation (proposal files, certifications, etc.)."""
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name='documents')
    document = models.FileField(upload_to='quotation_documents/')
    filename = models.CharField(max_length=255)
    file_size = models.IntegerField(default=0, help_text="File size in bytes")
    description = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return self.filename


class QuotationApproval(models.Model):
    """Dual director approval workflow for quotation acceptance."""
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name='approvals')
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='quotation_approvals')
    approval_order = models.IntegerField(help_text="1=First Director, 2=Second Director")
    comments = models.TextField(blank=True)
    approved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Quotation Approval"
        verbose_name_plural = "Quotation Approvals"
        unique_together = ('quotation', 'approval_order')

    def __str__(self):
        return f"{self.quotation.quotation_number} - Approval {self.approval_order}"


class DutyRegister(models.Model):
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('checked_in', 'Checked In'),
        ('completed', 'Completed'),
        ('no_show', 'No Show'),
    ]
    provider = models.ForeignKey(ServiceProvider, on_delete=models.CASCADE, related_name='duty_registers')
    event = models.ForeignKey('events.Event', on_delete=models.CASCADE, related_name='duty_registers')
    scheduled_date = models.DateField()
    scheduled_start = models.TimeField()
    scheduled_end = models.TimeField()
    actual_check_in = models.DateTimeField(null=True, blank=True)
    actual_check_out = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.provider.company_name} - {self.event.name}"
