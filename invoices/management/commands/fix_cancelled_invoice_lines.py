from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from invoices.models import Invoice, InvoiceLine, LedgerEntry, Refund
from invoices.views import refresh_invoice


class Command(BaseCommand):
    help = (
        "Zero out invoice lines whose booking is cancelled but which are still "
        "billed, refresh the affected invoices, and (for stands that were already "
        "paid) raise a refund due. Idempotent: re-running once lines are zeroed "
        "does nothing."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Show what would change without writing anything.',
        )
        parser.add_argument(
            '--no-refunds', action='store_true',
            help='Zero the lines but do not create refund records.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        make_refunds = not options['no_refunds']

        lines = (
            InvoiceLine.objects
            .filter(booking__status='cancelled')
            .exclude(amount_incl=0)
            .select_related('booking', 'booking__stall', 'booking__exhibitor', 'invoice')
            .order_by('invoice_id', 'id')
        )

        if not lines.exists():
            self.stdout.write(self.style.SUCCESS('No cancelled-but-billed invoice lines found.'))
            return

        affected_invoice_ids = set()
        affected_exhibitor_ids = set()
        refunds_created = 0

        for line in lines:
            booking = line.booking
            original_amount = line.amount_incl or Decimal('0')
            refund_amount = min(booking.amount_paid or Decimal('0'), original_amount)

            stall_name = booking.stall.name if booking.stall else '-'
            self.stdout.write(
                f"  {line.invoice.invoice_number}  line {line.id}  "
                f"booking {booking.booking_reference}  stall {stall_name}  "
                f"billed R{original_amount}  paid R{booking.amount_paid or 0}  "
                f"refund R{refund_amount}"
            )

            if dry_run:
                continue

            with transaction.atomic():
                if make_refunds and refund_amount > 0 and not Refund.objects.filter(booking=booking).exists():
                    Refund.objects.create(
                        booking=booking,
                        amount=refund_amount,
                        status='pending',
                        reason='Stand cancelled - automatic cleanup of a legacy billable invoice line',
                        notes=f'Paid toward cancelled stand {stall_name}',
                    )
                    LedgerEntry.objects.create(
                        exhibitor=booking.exhibitor,
                        booking=booking,
                        entry_type='credit',
                        description=f'Booking cancelled - refund of R{refund_amount} due',
                        reference=booking.booking_reference,
                        debit=Decimal('0'),
                        credit=refund_amount,
                        balance=Decimal('0'),
                        entry_date=timezone.localdate(),
                    )
                    refunds_created += 1

                if not line.description.startswith('CANCELLED -'):
                    line.description = f"CANCELLED - {line.description}"
                line.amount_excl = Decimal('0')
                line.vat_amount = Decimal('0')
                line.amount_incl = Decimal('0')
                line.save(update_fields=['description', 'amount_excl', 'vat_amount', 'amount_incl'])

                booking.payment_status = 'unpaid'
                booking.amount_paid = Decimal('0')
                booking.balance_due = Decimal('0')
                booking.save(update_fields=['payment_status', 'amount_paid', 'balance_due'])

            affected_invoice_ids.add(line.invoice_id)
            affected_exhibitor_ids.add(booking.exhibitor_id)

        if dry_run:
            self.stdout.write(self.style.WARNING('Dry run - nothing was changed.'))
            return

        for invoice_id in affected_invoice_ids:
            refresh_invoice(Invoice.objects.get(pk=invoice_id))

        from portal.views import _recalculate_ledger_balances
        from accounts.models import User
        for exhibitor_id in affected_exhibitor_ids:
            user = User.objects.filter(pk=exhibitor_id).first()
            if user is not None:
                _recalculate_ledger_balances(user)

        self.stdout.write(self.style.SUCCESS(
            f'Done. {refunds_created} refund(s) created; '
            f'{len(affected_invoice_ids)} invoice(s) refreshed.'
        ))
