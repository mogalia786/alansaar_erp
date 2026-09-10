from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db import models
from django.conf import settings
from django.utils import timezone
from decimal import Decimal
from .models import ServiceProvider, RFQ, Quotation, QuotationDocument


def provider_login(request):
    if request.session.get('provider_id'):
        provider = ServiceProvider.objects.get(pk=request.session['provider_id'])
        if provider.must_change_password:
            return redirect('providers:change_password')
        return redirect('providers:dashboard')
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        try:
            provider = ServiceProvider.objects.get(email=email, is_active=True)
            if provider.check_password(password):
                request.session['provider_id'] = provider.pk
                request.session['provider_name'] = provider.company_name
                request.session['provider_service'] = provider.service_type
                if provider.must_change_password:
                    return redirect('providers:change_password')
                return redirect('providers:dashboard')
            else:
                messages.error(request, 'Invalid email or password.')
        except ServiceProvider.DoesNotExist:
            messages.error(request, 'Invalid email or password.')
    return render(request, 'providers/login.html', {'site_name': settings.SITE_NAME})


def provider_change_password(request):
    if not request.session.get('provider_id'):
        return redirect('providers:login')
    provider = get_object_or_404(ServiceProvider, pk=request.session['provider_id'])
    if request.method == 'POST':
        current = request.POST.get('current_password', '')
        new_pass = request.POST.get('new_password', '')
        confirm = request.POST.get('confirm_password', '')
        if not provider.check_password(current):
            messages.error(request, 'Current password is incorrect.')
        elif len(new_pass) < 6:
            messages.error(request, 'New password must be at least 6 characters.')
        elif new_pass != confirm:
            messages.error(request, 'Passwords do not match.')
        else:
            provider.set_password(new_pass)
            provider.must_change_password = False
            provider.save()
            messages.success(request, 'Password changed successfully.')
            return redirect('providers:dashboard')
    return render(request, 'providers/change_password.html', {'provider': provider})


def provider_logout(request):
    request.session.flush()
    return redirect('providers:login')


def provider_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.session.get('provider_id'):
            return redirect('providers:login')
        return view_func(request, *args, **kwargs)
    return wrapper


@provider_required
def provider_dashboard(request):
    provider = get_object_or_404(ServiceProvider, pk=request.session['provider_id'])
    from bookings.models import Booking
    from events.models import Event
    from django.utils import timezone
    from django.db.models import Count
    upcoming = Event.objects.filter(end_date__gte=timezone.now()).annotate(total_bookings=Count('bookings')).order_by('start_date')
    open_rfqs = RFQ.objects.filter(status='open', closing_date__gte=timezone.now()).select_related('category')
    my_quotations = Quotation.objects.filter(
        models.Q(provider=provider) | models.Q(submitter_email=provider.email)
    ).select_related('rfq').order_by('-submitted_at')[:5]
    notifications = provider.notifications.select_related('booking__stall', 'booking__exhibitor').filter(is_read=False)[:20]
    unread_count = provider.notifications.filter(is_read=False).count()
    return render(request, 'providers/dashboard.html', {
        'provider': provider,
        'events': upcoming,
        'open_rfqs': open_rfqs,
        'my_quotations': my_quotations,
        'notifications': notifications,
        'unread_count': unread_count,
    })


@provider_required
def provider_events(request):
    from events.models import Event
    events = Event.objects.all().order_by('-start_date')
    return render(request, 'providers/events.html', {'events': events})


@provider_required
def provider_event_detail(request, event_id):
    from events.models import Event
    from bookings.models import Booking
    event = get_object_or_404(Event, pk=event_id)
    provider = get_object_or_404(ServiceProvider, pk=request.session['provider_id'])
    bookings = event.bookings.all().select_related('stall__zone', 'exhibitor').prefetch_related('accessories__accessory')

    if request.method == 'POST':
        pk = request.POST.get('booking_id')
        action = request.POST.get('action')
        if pk and action:
            b = get_object_or_404(Booking, pk=pk)
            if action in ('complete_build', 'reset_build') and provider.service_type in ('stand_builder', 'electrical'):
                b.stand_build_completed = (action == 'complete_build')
                b.stand_build_completed_at = timezone.now() if action == 'complete_build' else None
                b.save()
                messages.success(request, f'{b.booking_reference} build {"complete" if action == "complete_build" else "reset"}.')
            elif action in ('complete_electrical', 'reset_electrical') and provider.service_type in ('stand_builder', 'electrical'):
                b.electrical_completed = (action == 'complete_electrical')
                b.electrical_completed_at = timezone.now() if action == 'complete_electrical' else None
                b.save()
                messages.success(request, f'{b.booking_reference} electrical {"complete" if action == "complete_electrical" else "reset"}.')
        return redirect('providers:event_detail', event_id=event_id)

    stand_related = [b for b in bookings if b.require_stand_build or b.has_stand_accessories]
    elec_related = [b for b in bookings if b.requires_power or b.requires_water or b.require_extra_plugs or b.require_extra_lights or b.has_electrical_accessories]

    return render(request, 'providers/event_detail.html', {
        'event': event,
        'bookings': bookings,
        'provider': provider,
        'stand_to_do_count': sum(1 for b in stand_related if not b.stand_build_completed),
        'stand_completed_count': sum(1 for b in stand_related if b.stand_build_completed),
        'elec_to_do_count': sum(1 for b in elec_related if not b.electrical_completed),
        'elec_completed_count': sum(1 for b in elec_related if b.electrical_completed),
    })


@provider_required
def mark_notifications_read(request, event_id):
    provider = get_object_or_404(ServiceProvider, pk=request.session['provider_id'])
    from django.shortcuts import redirect
    qs = provider.notifications.filter(is_read=False, booking__event_id=event_id)
    qs.update(is_read=True)
    return redirect('providers:event_detail', event_id=event_id)


@provider_required
def provider_my_quotations(request):
    provider = get_object_or_404(ServiceProvider, pk=request.session['provider_id'])
    quotations = Quotation.objects.filter(
        models.Q(provider=provider) | models.Q(submitter_email=provider.email)
    ).select_related('rfq').order_by('-submitted_at')
    return render(request, 'providers/my_quotations.html', {
        'provider': provider,
        'quotations': quotations,
    })
