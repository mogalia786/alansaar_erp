from decimal import Decimal

VAT_RATE = Decimal('0.15')


def embedded_vat(inclusive_amount, rate=VAT_RATE):
    """Return the VAT embedded within a VAT-inclusive amount."""
    inclusive_amount = Decimal(inclusive_amount or '0')
    return (inclusive_amount * Decimal(rate) / (Decimal('1') + Decimal(rate))).quantize(Decimal('0.01'))


def booking_totals(stall_price, electricity_deposit, accessories_total, vat_rate=VAT_RATE):
    """Compute booking money fields.

    Stall prices and accessory prices are VAT INCLUSIVE. The electricity
    deposit is a refundable deposit and is therefore not subject to VAT.

    Returns (subtotal, vat_amount) where subtotal is the full amount payable
    by the exhibitor (VAT already included). vat_rate is a fraction, e.g. 0.15 for 15%.
    """
    taxable = Decimal(stall_price or '0') + Decimal(accessories_total or '0')
    vat = embedded_vat(taxable, rate=vat_rate)
    subtotal = taxable + Decimal(electricity_deposit or '0')
    return subtotal, vat