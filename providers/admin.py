from django.contrib import admin
from .models import ServiceProvider, ServiceQuotation, DutyRegister, RFQCategory, RFQ, Quotation, QuotationDocument, QuotationApproval

admin.site.register(ServiceProvider)
admin.site.register(ServiceQuotation)
admin.site.register(DutyRegister)
admin.site.register(RFQCategory)
admin.site.register(RFQ)
admin.site.register(Quotation)
admin.site.register(QuotationDocument)
admin.site.register(QuotationApproval)
