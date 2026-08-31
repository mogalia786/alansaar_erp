from django.contrib import admin
from .models import Invoice, Payment, PaymentReminder, LedgerEntry, Receipt, DebtDeclaration, DebtPaymentSchedule, DebtDeclarationApproval

admin.site.register(Invoice)
admin.site.register(Payment)
admin.site.register(PaymentReminder)
admin.site.register(LedgerEntry)
admin.site.register(Receipt)
admin.site.register(DebtDeclaration)
admin.site.register(DebtPaymentSchedule)
admin.site.register(DebtDeclarationApproval)
