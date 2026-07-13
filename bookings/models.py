from django.db import models
from django.conf import settings
from decimal import Decimal


class Booking(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
        ('confirmed', 'Confirmed (Paid)'),
        ('completed', 'Completed'),
    ]
    PAYMENT_STATUS = [
        ('unpaid', 'Unpaid'),
        ('deposit', 'Deposit Paid'),
        ('partial', 'Partially Paid'),
        ('paid', 'Paid in Full'),
    ]
    booking_reference = models.CharField(max_length=20, unique=True)
    event = models.ForeignKey('events.Event', on_delete=models.CASCADE, related_name='bookings')
    exhibitor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bookings')
    stall = models.ForeignKey('events.Stall', on_delete=models.CASCADE, related_name='bookings')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='unpaid')
    stall_price = models.DecimalField(max_digits=10, decimal_places=2)
    accessories_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    electricity_deposit = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('500.00'))
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    vat_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    balance_due = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    fascia_name = models.CharField(max_length=28, blank=True, help_text="Name on fascia board (max 28 chars)")
    terms_accepted = models.BooleanField(default=False)
    requires_power = models.BooleanField(default=False)
    power_amps = models.IntegerField(default=0, help_text="Additional power required in amps")
    requires_water = models.BooleanField(default=False)
    require_stand_build = models.BooleanField(default=False)
    SIDE_WALL_CHOICES = [('none', 'None'), ('left', 'Remove Left'), ('right', 'Remove Right'), ('both', 'Remove Both')]
    require_remove_side_walls = models.BooleanField(default=False)
    side_wall_removal = models.CharField(max_length=10, choices=SIDE_WALL_CHOICES, default='none')
    require_floor_mat = models.BooleanField(default=False)
    require_carpet = models.BooleanField(default=False)
    require_extra_plugs = models.BooleanField(default=False, help_text="Extra power plugs required")
    require_extra_lights = models.BooleanField(default=False, help_text="Extra lighting required")
    require_additional_power_amps = models.IntegerField(default=0, help_text="Additional power amps (15 or 30)")
    stand_build_instructions = models.TextField(blank=True, help_text="Special stand build instructions")
    exhibitor_requirements = models.TextField(blank=True, help_text="Exhibitor's special requirements")
    special_requirements = models.TextField(blank=True)
    admin_notes = models.TextField(blank=True)
    stand_build_completed = models.BooleanField(default=False)
    electrical_completed = models.BooleanField(default=False)
    requirements_version = models.IntegerField(default=0, help_text="Incremented when exhibitor changes requirements")
    requirements_updated_at = models.DateTimeField(null=True, blank=True)
    booking_date = models.DateTimeField(auto_now_add=True)
    approved_date = models.DateTimeField(null=True, blank=True)
    confirmed_date = models.DateTimeField(null=True, blank=True)
    payment_due_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['-booking_date']

    def __str__(self):
        return f"{self.booking_reference} - {self.exhibitor.company_name}"


class BookingAccessory(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='accessories')
    accessory = models.ForeignKey('events.AccessoryType', on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=8, decimal_places=2)

    def __str__(self):
        return f"{self.accessory.name} x {self.quantity}"


class DiscountRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved_by_first', 'Approved by First Admin'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='discount_requests')
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='discount_requests')
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.TextField()
    approved_by_first = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='first_approved_discounts')
    approved_by_second = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='second_approved_discounts')
    rejected_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='rejected_discounts')
    rejected_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Discount {self.discount_percent}% - {self.booking.booking_reference}"
