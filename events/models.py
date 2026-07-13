from django.db import models
from django.conf import settings


class Venue(models.Model):
    name = models.CharField(max_length=200)
    address = models.TextField()
    city = models.CharField(max_length=100, default='Durban')
    province = models.CharField(max_length=100, default='KwaZulu-Natal')
    width_meters = models.DecimalField(max_digits=6, decimal_places=2, default=50)
    length_meters = models.DecimalField(max_digits=6, decimal_places=2, default=30)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Event(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('ongoing', 'Ongoing'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    venue = models.ForeignKey(Venue, on_delete=models.CASCADE, related_name='events')
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    organizer_name = models.CharField(max_length=200, blank=True)
    organizer_email = models.EmailField(blank=True)
    organizer_phone = models.CharField(max_length=20, blank=True)
    website = models.URLField(blank=True)
    logo = models.ImageField(upload_to='event_logos/', blank=True, null=True)
    is_public = models.BooleanField(default=False)
    booking_open = models.BooleanField(default=False)
    max_stalls_per_exhibitor = models.PositiveIntegerField(default=5)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.name} ({self.venue})"


class FloorPlan(models.Model):
    event = models.OneToOneField(Event, on_delete=models.CASCADE, related_name='floor_plan')
    image = models.ImageField(upload_to='floor_plans/')
    original_width = models.IntegerField(default=1600, help_text="Original canvas width in pixels")
    original_height = models.IntegerField(default=900, help_text="Original canvas height in pixels")
    scale_factor = models.FloatField(default=40.0, help_text="Pixels per meter")
    hall_width_meters = models.DecimalField(max_digits=6, decimal_places=2, default=50.00)
    hall_height_meters = models.DecimalField(max_digits=6, decimal_places=2, default=30.00)
    walkway_width_meters = models.DecimalField(max_digits=5, decimal_places=2, default=3.00)
    calibration_x1 = models.FloatField(default=0)
    calibration_y1 = models.FloatField(default=0)
    calibration_x2 = models.FloatField(default=0)
    calibration_y2 = models.FloatField(default=0)
    calibration_distance_meters = models.FloatField(default=0)
    walkways_json = models.TextField(blank=True)
    exit_markers_json = models.TextField(blank=True)
    grid_spacing_px = models.IntegerField(default=20, help_text="Editor grid spacing in pixels")
    snap_to_grid_px = models.IntegerField(default=20, help_text="Snap increment in pixels (set equal to grid_spacing_px for 1-grid snap)")
    notes = models.TextField(blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Floor Plan'
        verbose_name_plural = 'Floor Plans'

    def __str__(self):
        return f"Floor Plan - {self.event.name}"

    @property
    def pixels_per_meter(self):
        if self.calibration_x1 and self.calibration_x2 and self.calibration_distance_meters:
            import math
            dx = self.calibration_x2 - self.calibration_x1
            dy = self.calibration_y2 - self.calibration_y1
            pixel_dist = math.sqrt(dx*dx + dy*dy)
            if pixel_dist and self.calibration_distance_meters:
                return pixel_dist / self.calibration_distance_meters
        return self.scale_factor

    def meters_to_pixels(self, meters):
        return int(meters * self.pixels_per_meter)

    def pixels_to_meters(self, pixels):
        if self.pixels_per_meter:
            return pixels / self.pixels_per_meter
        return 0


class Zone(models.Model):
    ZONE_TYPES = [
        ('exhibition', 'Exhibition Area'),
        ('food', 'Food Court'),
        ('entertainment', 'Entertainment'),
        ('service', 'Service Area'),
        ('entrance', 'Entrance/Exit'),
        ('restroom', 'Restrooms'),
        ('aisle', 'Aisle (Non-bookable)'),
        ('parking', 'Parking'),
    ]
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='zones')
    name = models.CharField(max_length=100)
    zone_type = models.CharField(max_length=20, choices=ZONE_TYPES, default='exhibition')
    color = models.CharField(max_length=20, default='#3498db')
    is_bookable = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.event.name})"


class Stall(models.Model):
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('reserved', 'Reserved'),
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('blocked', 'Blocked'),
    ]
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='stalls')
    zone = models.ForeignKey(Zone, on_delete=models.SET_NULL, null=True, blank=True, related_name='stalls')
    name = models.CharField(max_length=50)
    stall_prefix = models.CharField(max_length=10, default='Stand', help_text="Prefix for numbering (Stand, Food, Kiddies)")
    position_x = models.IntegerField(default=0, help_text="X position in mm on floor plan")
    position_y = models.IntegerField(default=0, help_text="Y position in mm on floor plan")
    width = models.IntegerField(default=3000, help_text="Width in mm on floor plan")
    height = models.IntegerField(default=3000, help_text="Height in mm on floor plan")
    size_sqm = models.DecimalField(max_digits=6, decimal_places=2, default=9.00)
    base_price = models.DecimalField(max_digits=10, decimal_places=2, default=5000)
    corner_premium = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    has_water = models.BooleanField(default=False)
    has_wifi = models.BooleanField(default=False)
    is_corner = models.BooleanField(default=False)
    is_near_entrance = models.BooleanField(default=False)
    is_accessible = models.BooleanField(default=False)
    entrance_premium = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    max_electricity_amps = models.IntegerField(default=15, help_text="Max amps available")
    num_tables = models.PositiveIntegerField(default=1, help_text="Tables included with this stall")
    num_chairs = models.PositiveIntegerField(default=2, help_text="Chairs included with this stall")
    electrical_instructions = models.TextField(blank=True, help_text="Electrician instructions for this stall position")
    build_instructions = models.TextField(blank=True, help_text="Stand builder instructions for this stall position")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        unique_together = ['event', 'name']

    def __str__(self):
        return f"{self.name} ({self.event.name})"

    @property
    def total_price(self):
        return self.base_price + self.corner_premium + self.entrance_premium


class AccessoryType(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    unit = models.CharField(max_length=50, default='per unit')
    icon = models.CharField(max_length=50, blank=True, help_text="FontAwesome icon")
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['display_order']

    def __str__(self):
        return f"{self.name} - R{self.price}"
