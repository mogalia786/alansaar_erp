from django.contrib import admin
from .models import Venue, Event, FloorPlan, Zone, Stall, AccessoryType

admin.site.register(Venue)
admin.site.register(Event)
admin.site.register(FloorPlan)
admin.site.register(Zone)
admin.site.register(Stall)
admin.site.register(AccessoryType)
