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
    is_verified = models.BooleanField(default=False)
    role = models.ForeignKey('Role', null=True, blank=True, on_delete=models.SET_NULL, related_name='users')

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self):
        return self.get_full_name() or self.username

    def has_erp_permission(self, section, action='view'):
        if self.user_type in ('superadmin', 'admin'):
            return True
        if self.user_type == 'director' and section in ('accounting', 'reports', 'expenses', 'rfq'):
            return True
        if self.user_type == 'finance' and section in ('accounting', 'reports', 'invoices', 'payments', 'expenses'):
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
        ('rfq', 'RFQ / Procurement'),
        ('accounting', 'Accounting'),
        ('reports', 'Reports'),
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
