from django.contrib import admin
from .models import Booking, BookingAccessory, DiscountRequest

admin.site.register(Booking)
admin.site.register(BookingAccessory)
admin.site.register(DiscountRequest)
