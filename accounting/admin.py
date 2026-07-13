from django.contrib import admin
from .models import Account, JournalEntry, JournalLine


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'type', 'is_active']
    list_filter = ['type', 'is_active']
    search_fields = ['code', 'name']


class JournalLineInline(admin.TabularInline):
    model = JournalLine
    extra = 2


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ['entry_number', 'date', 'description', 'is_posted', 'created_at']
    list_filter = ['is_posted', 'date']
    inlines = [JournalLineInline]
