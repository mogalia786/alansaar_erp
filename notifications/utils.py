import logging
from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.html import strip_tags
from notifications.models import Notification
from decimal import Decimal

logger = logging.getLogger(__name__)

User = None  # lazy import


def get_director_emails():
    global User
    if User is None:
        from django.contrib.auth import get_user_model
        User = get_user_model()
    return list(
        User.objects.filter(user_type='director', is_active=True)
        .values_list('email', flat=True)
        .distinct()
    )


def send_html_email(subject, template_name, context, to_emails, from_email=None):
    if not to_emails:
        return
    if isinstance(to_emails, str):
        to_emails = [to_emails]
    html = render_to_string(template_name, context)
    text = strip_tags(html)
    msg = EmailMultiAlternatives(
        subject=subject,
        body=text,
        from_email=from_email or settings.DEFAULT_FROM_EMAIL,
        to=to_emails,
    )
    msg.attach_alternative(html, 'text/html')
    if settings.DEBUG:
        print(f"\n{'='*60}\nEMAIL TO: {to_emails}\nSUBJECT: {subject}\n{'='*60}\n{text}\n{'='*60}\n")
    try:
        msg.send(fail_silently=False)
    except Exception as e:
        print(f"Email send failed: {e}")


def create_notification(user, ntype, title, message, link=''):
    Notification.objects.create(
        user=user, notification_type=ntype,
        title=title, message=message, link=link,
    )


def send_booking_confirmation(booking):
    exhibitor = booking.exhibitor
    subject = f'Booking Confirmed - {booking.booking_reference} - Al Ansaar Foundation'
    context = {
        'booking': booking,
        'exhibitor': exhibitor,
        'site_name': settings.SITE_NAME,
        'site_url': settings.SITE_URL,
    }
    to_email = [exhibitor.email]
    send_html_email(subject, 'emails/booking_confirmation.html', context, to_email)
    create_notification(
        exhibitor, 'booking',
        f'Booking {booking.booking_reference} Confirmed',
        f'Your stall {booking.stall.name} at {booking.event.name} has been confirmed.',
        f'/bookings/{booking.pk}/'
    )


def send_payment_received(payment):
    from django.contrib.auth import get_user_model
    exhibitor = payment.booking.exhibitor
    amt = f"{payment.amount:.2f}"
    context = {
        'payment': payment,
        'booking': payment.booking,
        'exhibitor': exhibitor,
        'invoice': payment.invoice,
        'site_name': settings.SITE_NAME,
        'site_url': settings.SITE_URL,
    }

    # Notify directors via email
    admin_recipients = get_director_emails()
    if admin_recipients:
        send_html_email(
            f'Payment to Verify - R{amt} - {exhibitor.company_name}',
            'emails/admin_payment_notification.html', context, admin_recipients
        )

    # In-app notification for all staff users
    User = get_user_model()
    for staff in User.objects.filter(is_staff=True):
        create_notification(
            staff, 'payment',
            f'Payment to Verify - R{amt}',
            f'{exhibitor.company_name} submitted a payment of R{amt} for {payment.invoice.invoice_number}.',
            f'/erp/payments/'
        )

    # Notify exhibitor
    send_html_email(
        f'Payment Received - {payment.invoice.invoice_number} - Al Ansaar Foundation',
        'emails/payment_received.html', context, [exhibitor.email]
    )
    create_notification(
        exhibitor, 'payment',
        f'Payment of R{amt} Received',
        f'Your payment of R{amt} for invoice {payment.invoice.invoice_number} has been received and is pending verification.',
        f'/invoices/{payment.invoice.pk}/'
    )


def send_payment_verified(payment, receipt):
    exhibitor = payment.booking.exhibitor
    amt = f"{payment.amount:.2f}"
    context = {
        'payment': payment,
        'booking': payment.booking,
        'exhibitor': exhibitor,
        'invoice': payment.invoice,
        'receipt': receipt,
        'site_name': settings.SITE_NAME,
        'site_url': settings.SITE_URL,
    }
    send_html_email(
        f'Payment Verified - {payment.invoice.invoice_number} - Al Ansaar Foundation',
        'emails/payment_verified.html', context, [exhibitor.email]
    )
    create_notification(
        exhibitor, 'payment',
        f'Payment of R{amt} Verified',
        f'Your payment of R{amt} for {payment.invoice.invoice_number} has been verified. Receipt: {receipt.receipt_number}.',
        f'/invoices/{payment.invoice.pk}/'
    )


def send_discount_request(dr):
    subject = f'Discount Request - {dr.discount_percent}% - {dr.booking.booking_reference}'
    context = {
        'dr': dr,
        'booking': dr.booking,
        'requested_by': dr.requested_by,
        'site_name': settings.SITE_NAME,
        'site_url': settings.SITE_URL,
    }
    admin_emails = get_director_emails()
    if settings.DEBUG:
        print(f'[send_discount_request] Director emails: {admin_emails}')
    if admin_emails:
        try:
            send_html_email(subject, 'emails/discount_request.html', context, admin_emails)
        except Exception as e:
            if settings.DEBUG:
                print(f'[send_discount_request] Email send exception: {e}')
    else:
        if settings.DEBUG:
            print('[send_discount_request] No director emails found!')

    create_notification(
        dr.requested_by, 'discount',
        f'Discount Request Submitted ({dr.discount_percent}%)',
        f'Your discount request for {dr.booking.booking_reference} is pending approval.',
        f'/bookings/{dr.booking.pk}/'
    )


def send_discount_decision(dr):
    exhibitor = dr.booking.exhibitor
    all_emails = get_director_emails()
    if dr.status == 'approved':
        subject = f'Discount Approved - {dr.discount_percent}% - {dr.booking.booking_reference}'
        ntitle = f'Discount of {dr.discount_percent}% Approved'
        nmsg = f'Your discount request for {dr.booking.booking_reference} has been approved.'
    elif dr.status == 'rejected':
        subject = f'Discount Declined - {dr.booking.booking_reference}'
        ntitle = f'Discount Request Declined'
        nmsg = f'Your discount request for {dr.booking.booking_reference} was declined.'
    else:
        return
    context = {'dr': dr, 'booking': dr.booking, 'subject': subject}
    recipients = list(set([exhibitor.email] + all_emails))
    if settings.DEBUG:
        print(f'[send_discount_decision] Status: {dr.status}, Recipients: {recipients}')
    send_html_email(subject, 'emails/discount_decision.html', context, recipients)
    create_notification(exhibitor, 'discount', ntitle, nmsg, f'/bookings/{dr.booking.pk}/')


def send_welcome_email(user):
    subject = 'Welcome to Al Ansaar Foundation \u2013 Registration Successful'
    context = {
        'user': user,
        'site_name': settings.SITE_NAME,
        'site_url': settings.SITE_URL,
    }
    send_html_email(subject, 'emails/welcome.html', context, [user.email])
    create_notification(
        user, 'account',
        'Welcome to Al Ansaar Foundation',
        'Your exhibitor account has been created. You can now browse and book stalls.',
        '/dashboard/'
    )


def send_invoice_email(invoice, trigger='created'):
    if trigger == 'created':
        subject = f'Invoice {invoice.invoice_number} - Al Ansaar Foundation'
        template = 'emails/invoice_created.html'
        amt = f"{invoice.amount_incl:.2f}"
        ntitle = f'Invoice {invoice.invoice_number} Issued'
        nmsg = f'Invoice {invoice.invoice_number} for R{amt} has been issued. Due: {invoice.due_date}.'
    elif trigger == 'payment_received':
        subject = f'Payment Submitted - Invoice {invoice.invoice_number}'
        template = 'emails/payment_submitted.html'
        ntitle = f'Payment Submitted'
        nmsg = f'Your payment for invoice {invoice.invoice_number} is pending verification.'
    else:
        return
    context = {'invoice': invoice, 'site_name': settings.SITE_NAME, 'site_url': settings.SITE_URL}
    send_html_email(subject, template, context, [invoice.exhibitor.email])
    create_notification(invoice.exhibitor, 'invoice', ntitle, nmsg, f'/invoices/{invoice.pk}/')


def send_rfq_published(rfq):
    """Notify all active service providers about a new RFQ."""
    from providers.models import ServiceProvider
    subject = f'NEW: Request for Proposals - {rfq.rfq_number} - {rfq.title[:60]} - Al Ansaar Foundation'
    context = {
        'rfq': rfq,
        'site_name': settings.SITE_NAME,
        'site_url': settings.SITE_URL,
    }
    providers = ServiceProvider.objects.filter(is_active=True)
    for p in providers:
        try:
            send_html_email(subject, 'emails/rfq_published.html', context, [p.email])
        except Exception as e:
            logger.warning(f'Failed to send RFQ email to {p.email}: {e}')
    # Notify internal ERP staff
    from django.contrib.auth import get_user_model
    User = get_user_model()
    for user in User.objects.filter(is_staff=True, is_active=True):
        create_notification(
            user, 'rfq',
            f'RFQ Published: {rfq.rfq_number}',
            f'{rfq.title[:100]} - Closes: {rfq.closing_date.strftime("%d %b %Y %H:%M")}',
            f'/erp/rfqs/{rfq.pk}/'
        )


def send_quotation_submitted(quotation):
    """Notify ERP staff when a quotation is submitted."""
    rfq = quotation.rfq
    submitter = quotation.provider.company_name if quotation.provider else quotation.submitter_company_name
    subject = f'Quotation Received - {quotation.quotation_number} - {submitter}'
    context = {
        'quotation': quotation,
        'rfq': rfq,
        'site_name': settings.SITE_NAME,
        'site_url': settings.SITE_URL,
    }
    # Email to procurement/system email
    to_emails = [settings.DEFAULT_FROM_EMAIL]
    director_emails = get_director_emails()
    if director_emails:
        to_emails = list(set(to_emails + director_emails))
    send_html_email(subject, 'emails/quotation_submitted.html', context, to_emails)
    # In-app notification for all staff
    from django.contrib.auth import get_user_model
    User = get_user_model()
    for user in User.objects.filter(is_staff=True, is_active=True):
        create_notification(
            user, 'rfq',
            f'Quotation: {quotation.quotation_number}',
            f'{submitter} submitted a quotation for {rfq.rfq_number} - R{quotation.total_amount_incl:.2f}',
            f'/erp/rfqs/{rfq.pk}/'
        )


def send_quotation_accepted(quotation, provider_password=None):
    """Notify provider that their proposal has been accepted (pending site meeting)."""
    rfq = quotation.rfq
    recipient_email = quotation.provider.email if quotation.provider else quotation.submitter_email
    subject = f'Proposal Accepted - {quotation.quotation_number} - {rfq.rfq_number} - Al Ansaar Foundation'
    context = {
        'quotation': quotation,
        'rfq': rfq,
        'site_name': settings.SITE_NAME,
        'site_url': settings.SITE_URL,
        'provider_password': provider_password,
    }
    send_html_email(
        subject, 'emails/quotation_accepted.html', context, [recipient_email]
    )
    # Notifications for internal ERP staff only
    from django.contrib.auth import get_user_model
    User = get_user_model()
    for user in User.objects.filter(is_staff=True, is_active=True):
        create_notification(
            user, 'rfq',
            'Proposal Accepted',
            f'Quotation {quotation.quotation_number} for {rfq.rfq_number} has been accepted pending approval. Awaiting site meeting.',
            f'/erp/quotations/{quotation.pk}/'
        )


def send_quotation_site_meeting(quotation, meeting_date):
    """Notify provider of scheduled site meeting."""
    rfq = quotation.rfq
    recipient_email = quotation.provider.email if quotation.provider else quotation.submitter_email
    subject = f'Site Meeting Scheduled - {quotation.quotation_number} - Al Ansaar Foundation'
    context = {
        'quotation': quotation,
        'rfq': rfq,
        'meeting_date': meeting_date,
        'site_name': settings.SITE_NAME,
        'site_url': settings.SITE_URL,
    }
    send_html_email(
        subject, 'emails/quotation_site_meeting.html', context, [recipient_email]
    )
    # Notifications for internal ERP staff only
    from django.contrib.auth import get_user_model
    User = get_user_model()
    for user in User.objects.filter(is_staff=True, is_active=True):
        create_notification(
            user, 'rfq',
            'Site Meeting Scheduled',
            f'Site meeting scheduled for {meeting_date.strftime("%d %b %Y at %H:%M")} regarding {quotation.quotation_number}.',
            f'/erp/quotations/{quotation.pk}/'
        )


def send_quotation_fully_approved(quotation):
    """Notify provider that their quotation is fully approved after site meeting."""
    rfq = quotation.rfq
    provider = quotation.provider
    if not provider:
        return
    recipient_email = provider.email
    provider_name = provider.company_name
    subject = f'Quotation Fully Approved - {quotation.quotation_number} - Al Ansaar Foundation'
    context = {
        'quotation': quotation,
        'rfq': rfq,
        'site_name': settings.SITE_NAME,
        'site_url': settings.SITE_URL,
    }
    send_html_email(
        subject, 'emails/quotation_fully_approved.html', context, [recipient_email]
    )
    # Notifications for internal ERP staff only
    from django.contrib.auth import get_user_model
    User = get_user_model()
    for user in User.objects.filter(is_staff=True, is_active=True):
        create_notification(
            user, 'rfq',
            'Quotation Fully Approved',
            f'Quotation {quotation.quotation_number} for {rfq.rfq_number} has been fully approved after site meeting.',
            f'/erp/quotations/{quotation.pk}/'
        )


def send_quotation_rejected(quotation):
    """Notify provider that their proposal was not accepted."""
    rfq = quotation.rfq
    recipient_email = quotation.provider.email if quotation.provider else quotation.submitter_email
    if not recipient_email:
        return
    subject = f'Proposal Status Update - {quotation.quotation_number} - Al Ansaar Foundation'
    context = {
        'quotation': quotation,
        'rfq': rfq,
        'site_name': settings.SITE_NAME,
        'site_url': settings.SITE_URL,
    }
    send_html_email(
        subject, 'emails/quotation_rejected.html', context, [recipient_email]
    )


def send_requirements_update(booking, changed_by):
    """Email providers when exhibitor changes booking requirements."""
    from providers.models import ServiceProvider
    subject = f'REQUIREMENTS CHANGED - {booking.booking_reference} - {booking.exhibitor.company_name}'
    context = {
        'booking': booking,
        'changed_by': changed_by,
        'site_name': settings.SITE_NAME,
        'site_url': settings.SITE_URL,
    }
    providers = ServiceProvider.objects.filter(
        is_active=True,
        service_type__in=['stand_builder', 'electrical'],
    )
    for p in providers:
        send_html_email(subject, 'emails/requirements_updated.html', context, [p.email])
    create_notification(
        booking.exhibitor, 'booking',
        f'Requirements Updated (v{booking.requirements_version})',
        f'Your requirements for {booking.booking_reference} have been saved and notified to providers.',
        f'/bookings/{booking.pk}/'
    )

