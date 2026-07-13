from django import template
from decimal import Decimal

register = template.Library()

@register.filter
def sum_attr(value, attr):
    total = Decimal('0')
    for item in value:
        val = getattr(item, attr, None) if hasattr(item, attr) else item.get(attr, 0)
        if val is None:
            val = 0
        total += Decimal(str(val))
    return total


@register.filter(name='has_perm')
def has_perm(user, section_action):
    parts = section_action.split(':')
    section = parts[0]
    action = parts[1] if len(parts) > 1 else 'view'
    if not user.is_authenticated:
        return False
    return user.has_erp_permission(section, action)
