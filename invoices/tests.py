from decimal import Decimal

from django.test import TestCase
from django.contrib.auth import get_user_model

from events.models import Venue, Event, Zone, Stall
from bookings.models import Booking
from invoices.models import Invoice, Payment
from invoices.views import ensure_booking_invoice, refresh_invoice

User = get_user_model()


class PaymentStandAllocationTests(TestCase):
    """A payment made for one stand must be reflected on THAT stand, not on
    whichever stand happens to be billed first on the consolidated invoice."""

    def setUp(self):
        self.venue = Venue.objects.create(
            name='Test Venue', address='1 Test Rd',
            width_meters=100, length_meters=80,
        )
        self.event = Event.objects.create(
            name='Allocation Event', venue=self.venue,
            start_date='2026-12-01', end_date='2026-12-31',
            status='published', booking_open=True, is_public=True,
            vat_rate=Decimal('0.00'),
        )
        self.zone = Zone.objects.create(
            event=self.event, name='Hall 1', zone_type='exhibition',
            color='#5B2C6F', is_bookable=True,
        )
        self.exhibitor = User.objects.create_user(
            username='alloc_exhibitor', email='alloc@test.com',
            password='pass12345', user_type='exhibitor',
            company_name='Allocation Co',
        )

        self.bookings = []
        self.invoice = None
        for i, name in enumerate(['S1', 'S2', 'S3'], start=1):
            stall = Stall.objects.create(
                event=self.event, zone=self.zone, name=name,
                status='available', width=3000, height=3000,
                size_sqm=9, base_price=Decimal('3000.00'),
            )
            booking = Booking.objects.create(
                booking_reference=f'ALLOC-{i}',
                event=self.event, exhibitor=self.exhibitor, stall=stall,
                stall_price=Decimal('3000.00'),
                electricity_deposit=Decimal('500.00'),
                subtotal=Decimal('3500.00'),
                total_amount=Decimal('3500.00'),
                balance_due=Decimal('3500.00'),
                requires_power=True,
                status='pending', payment_status='unpaid',
            )
            inv, _ = ensure_booking_invoice(booking)
            self.invoice = inv
            self.bookings.append(booking)

    def _paid(self):
        for b in self.bookings:
            b.refresh_from_db()
        return {b.booking_reference: b.amount_paid for b in self.bookings}

    def test_payment_tagged_to_later_stand_lands_on_that_stand(self):
        """Pay stand 3 in full -> only stand 3 should show as paid."""
        target = self.bookings[2]  # S3 (last line)
        Payment.objects.create(
            invoice=self.invoice, booking=target,
            amount=Decimal('3500.00'), payment_method='eft',
            status='verified', verified_by=self.exhibitor,
        )
        refresh_invoice(self.invoice)

        paid = self._paid()
        self.assertEqual(paid['ALLOC-3'], Decimal('3500.00'))
        self.assertEqual(paid['ALLOC-1'], Decimal('0'))
        self.assertEqual(paid['ALLOC-2'], Decimal('0'))

    def test_full_invoice_payment_tagged_to_one_stand_settles_all_stands(self):
        """An over-payment on one stand spills to the exhibitor's other stands."""
        Payment.objects.create(
            invoice=self.invoice, booking=self.bookings[0],
            amount=Decimal('10500.00'), payment_method='eft',
            status='verified', verified_by=self.exhibitor,
        )
        refresh_invoice(self.invoice)

        paid = self._paid()
        self.assertEqual(paid['ALLOC-1'], Decimal('3500.00'))
        self.assertEqual(paid['ALLOC-2'], Decimal('3500.00'))
        self.assertEqual(paid['ALLOC-3'], Decimal('3500.00'))

    def test_untagged_payment_spreads_in_line_order(self):
        """Legacy payments with no stand tag are still spread across stands."""
        Payment.objects.create(
            invoice=self.invoice, booking=None,
            amount=Decimal('3500.00'), payment_method='eft',
            status='verified', verified_by=self.exhibitor,
        )
        refresh_invoice(self.invoice)

        paid = self._paid()
        self.assertEqual(paid['ALLOC-1'], Decimal('3500.00'))
        self.assertEqual(paid['ALLOC-2'], Decimal('0'))
        self.assertEqual(paid['ALLOC-3'], Decimal('0'))
