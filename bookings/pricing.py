from decimal import Decimal

# NPO: no VAT is charged on exhibitor invoices. Kept as a constant for
# backward compatibility with call sites.
VAT_RATE = Decimal('0')


def embedded_vat(inclusive_amount, rate=VAT_RATE):
    """Return the VAT embedded within an amount. Always 0 — VAT not charged."""
    return Decimal('0')


def booking_totals(stall_price, electricity_deposit, accessories_total, vat_rate=VAT_RATE):
    """Compute booking money fields. No VAT is charged (NPO).

    Returns (subtotal, vat_amount) where subtotal is the full amount payable
    by the exhibitor and vat_amount is always zero.
    """
    subtotal = Decimal(stall_price or '0') + Decimal(accessories_total or '0') + Decimal(electricity_deposit or '0')
    return subtotal, Decimal('0')
