from django.contrib import admin
from .models import Venue, Event, FloorPlan, FloorPlanSection, Zone, Stall, AccessoryType

admin.site.register(Venue)
admin.site.register(Event)
admin.site.register(FloorPlan)
admin.site.register(FloorPlanSection)
admin.site.register(Zone)
admin.site.register(Stall)


@admin.register(AccessoryType)
class AccessoryTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price', 'unit', 'is_active', 'display_order')
    list_editable = ('category', 'price', 'is_active', 'display_order')
    list_filter = ('category', 'is_active')
