from django.contrib import admin
from .models import Invoice, Payment, PaymentReminder, LedgerEntry, Receipt

admin.site.register(Invoice)
admin.site.register(Payment)
admin.site.register(PaymentReminder)
admin.site.register(LedgerEntry)
admin.site.register(Receipt)
