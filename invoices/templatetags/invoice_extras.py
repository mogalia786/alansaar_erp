from django import template
from django.db.models import Sum
from decimal import Decimal

register = template.Library()


@register.filter
def pending_payments_total(invoice):
    return invoice.payments.filter(status='pending').aggregate(
        s=Sum('amount')
    )['s'] or Decimal('0')


@register.filter
def effective_balance(invoice):
    pending = invoice.payments.filter(status='pending').aggregate(
        s=Sum('amount')
    )['s'] or Decimal('0')
    return invoice.amount_incl - invoice.amount_paid - pending
