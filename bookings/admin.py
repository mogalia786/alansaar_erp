from django.contrib import admin
from .models import Booking, BookingAccessory, DiscountRequest, StallTransferRequest

admin.site.register(Booking)
admin.site.register(BookingAccessory)
admin.site.register(DiscountRequest)
admin.site.register(StallTransferRequest)
