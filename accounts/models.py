from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    USER_TYPES = [
        ('exhibitor', 'Exhibitor'),
        ('staff', 'Staff'),
        ('director', 'Director'),
        ('finance', 'Finance'),
        ('service_provider', 'Service Provider'),
        ('admin', 'Admin'),
        ('superadmin', 'Super Admin'),
    ]
    user_type = models.CharField(max_length=20, choices=USER_TYPES, default='exhibitor')
    phone = models.CharField(max_length=20, blank=True)
    company_name = models.CharField(max_length=200, blank=True, help_text="For exhibitors")
    company_reg_number = models.CharField(max_length=50, blank=True, help_text="Company registration number")
    vat_number = models.CharField(max_length=50, blank=True, help_text="VAT number (if VAT registered)")
    address = models.TextField(blank=True, help_text="Physical address")
    proof_of_address = models.FileField(upload_to='proof_of_address/', blank=True, help_text="Proof of address (PDF, JPG, PNG)")
    photo = models.ImageField(upload_to='exhibitor_photos/', blank=True, help_text="Passport-style photo of the exhibitor")
    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    role = models.ForeignKey('Role', null=True, blank=True, on_delete=models.SET_NULL, related_name='users')

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self):
        return self.get_full_name() or self.username

    def has_erp_permission(self, section, action='view'):
        if self.user_type in ('superadmin', 'admin'):
            return True
        if self.user_type == 'director' and section in ('accounting', 'reports', 'booking_reports', 'expenses', 'rfq', 'gate_takings', 'debt_declarations'):
            return True
        if self.user_type == 'finance' and section in ('accounting', 'reports', 'booking_reports', 'invoices', 'payments', 'expenses', 'gate_takings', 'debt_declarations'):
            return True
        if self.role:
            return self.role.permissions.filter(section=section, **{f'can_{action}': True}).exists()
        return False


class Role(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class RolePermission(models.Model):
    SECTIONS = [
        ('dashboard', 'Dashboard'),
        ('events', 'Events'),
        ('floor_plan', 'Floor Plan'),
        ('bookings', 'Bookings'),
        ('invoices', 'Invoices'),
        ('payments', 'Payments'),
        ('exhibitors', 'Exhibitors'),
        ('providers', 'Service Providers'),
        ('expenses', 'Expenses'),
        ('gate_takings', 'Daily Gate Takings'),
        ('debt_declarations', 'Debt Declarations'),
        ('rfq', 'RFQ / Procurement'),
        ('accounting', 'Accounting'),
        ('reports', 'Reports'),
        ('booking_reports', 'Consolidated Bookings Reports'),
        ('users', 'User Management'),
    ]
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name='permissions')
    section = models.CharField(max_length=30, choices=SECTIONS)
    can_view = models.BooleanField(default=True)
    can_create = models.BooleanField(default=False)
    can_edit = models.BooleanField(default=False)
    can_delete = models.BooleanField(default=False)

    class Meta:
        unique_together = ('role', 'section')
        verbose_name = 'Role Permission'

    def __str__(self):
        return f"{self.role.name} - {self.get_section_display()}"
