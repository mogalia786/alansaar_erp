from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.db.models import Sum, Count, Q
from events.models import Event, FloorPlan, FloorPlanSection, Zone, Stall, AccessoryType
import re, json, os
from bookings.models import Booking, DiscountRequest
from invoices.models import Invoice, Payment, Receipt, LedgerEntry, DebtDeclaration, DebtPaymentSchedule, DebtDeclarationApproval
from accounts.models import User, Role, RolePermission
from providers.models import ServiceProvider, ServiceLog, Expense, RFQ, RFQCategory, Quotation, QuotationDocument, QuotationApproval
from django.utils import timezone
from decimal import Decimal
import json
import uuid
import os
from datetime import timedelta
from notifications.utils import (
    send_booking_confirmation, send_booking_received, send_payment_received,
    send_payment_verified as send_payment_verified_email,
    send_discount_request, send_discount_decision,
    send_invoice_email
)
from accounting.auto_post import auto_post_invoice, auto_post_payment


def is_staff_user(user):
    return user.is_authenticated and (user.is_staff or user.user_type in ['staff', 'finance', 'director', 'admin', 'superadmin'])


def is_admin_user(user):
    return user.is_authenticated and user.user_type in ('admin', 'superadmin')


def erp_login_required(view_fn):
    """Require staff-level login, redirecting to /erp/login/ instead of /login/."""
    from django.contrib.auth.decorators import login_required
    from django.contrib.auth.views import redirect_to_login
    from functools import wraps

    @wraps(view_fn)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), login_url='/erp/login/')
        if not is_staff_user(request.user):
            return redirect_to_login(request.get_full_path(), login_url='/erp/login/')
        return view_fn(request, *args, **kwargs)
    return wrapper


def erp_section_required(section, action='view'):
    """Decorator that checks the user's role has permission for a section."""
    from functools import wraps
    def decorator(view_fn):
        @wraps(view_fn)
        @erp_login_required
        def wrapper(request, *args, **kwargs):
            if request.user.user_type in ('admin', 'superadmin'):
                return view_fn(request, *args, **kwargs)
            if not request.user.has_erp_permission(section, action):
                messages.error(request, f'Access denied: no {action} permission for {section}.')
                return redirect('erp:dashboard')
            return view_fn(request, *args, **kwargs)
        return wrapper
    return decorator


@erp_login_required
def api_search_exhibitors(request):
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse([], safe=False)
    results = Booking.objects.filter(
        Q(exhibitor__company_name__icontains=q) |
        Q(fascia_name__icontains=q)
    ).values_list('exhibitor__company_name', 'fascia_name').distinct()[:20]
    seen = set()
    items = []
    for company, bk_fascia in results:
        label = bk_fascia or company or ''
        if label and label not in seen:
            seen.add(label)
            items.append({'label': label})
    return JsonResponse(items, safe=False)


def erp_login(request):
    if request.user.is_authenticated and is_staff_user(request.user):
        return redirect('erp:dashboard')
    if request.method == 'POST':
        user = authenticate(request, username=request.POST['username'], password=request.POST['password'])
        if user and user.is_staff:
            login(request, user)
            return redirect('erp:dashboard')
        messages.error(request, 'Invalid staff credentials.')
    return render(request, 'portal/login.html')


def erp_logout(request):
    logout(request)
    return redirect('erp:login')


@erp_login_required
def erp_dashboard(request):
    from accounting.models import GateTaking
    gt_agg = GateTaking.objects.aggregate(c=Sum('cash_amount'), card=Sum('card_amount'))
    gate_takings_total = (gt_agg['c'] or Decimal('0')) + (gt_agg['card'] or Decimal('0'))
    ctx = {
        'active_events': Event.objects.filter(status__in=['published', 'ongoing']).count(),
        'total_bookings': Booking.objects.count(),
        'pending_bookings': Booking.objects.filter(status='pending').count(),
        'pending_payments': Payment.objects.filter(status='pending').count(),
        'unverified_exhibitors': User.objects.filter(user_type='exhibitor', is_verified=False).count(),
        'total_revenue': (Decimal(Invoice.objects.aggregate(s=Sum('amount_paid'))['s'] or 0) + gate_takings_total),
        'gate_takings_total': gate_takings_total,
        'recent_bookings': Booking.objects.select_related('exhibitor', 'event', 'stall').order_by('-booking_date')[:10],
    }
    return render(request, 'portal/dashboard.html', ctx)


@erp_section_required('events')
def erp_event_list(request):
    events = Event.objects.all().select_related('venue')
    return render(request, 'portal/event_list.html', {'events': events})


@erp_section_required('events')
def erp_event_detail(request, event_id):
    event = get_object_or_404(Event.objects.select_related('venue'), pk=event_id)
    stalls = event.stalls.select_related('zone').all()
    stalls_available = stalls.filter(status='available').count()
    floor_plan = getattr(event, 'floor_plan', None)
    zones = event.zones.all()
    return render(request, 'portal/event_detail.html', {
        'event': event, 'stalls': stalls, 'stalls_available': stalls_available,
        'floor_plan': floor_plan, 'zones': zones,
    })


@erp_section_required('floor_plan')
def erp_floor_plan(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    floor_plan = getattr(event, 'floor_plan', None)
    sections = event.floor_plan_sections.all().order_by('display_order')
    active_section_id = request.GET.get('section')

    if sections.exists():
        if active_section_id:
            active_section = get_object_or_404(FloorPlanSection, pk=active_section_id, event=event)
        else:
            active_section = sections.first()

        stalls = event.stalls.filter(section=active_section).select_related('zone')
        scale = float(active_section.scale_factor)
        stalls_data = [{
            'id': s.id, 'name': s.name,
            'x': round(s.position_x * scale / 1000),
            'y': round(s.position_y * scale / 1000),
            'w': round(s.width * scale / 1000),
            'h': round(s.height * scale / 1000),
            'status': s.status,
            'price': float(s.total_price), 'is_corner': s.is_corner,
            'has_water': s.has_water, 'zone': s.zone_id,
            'size_sqm': float(s.size_sqm),
            'rotation': s.rotation,
        } for s in stalls]
        sections_data = [{
            'id': s.id, 'name': s.name,
            'image_url': s.section_image.url if s.section_image else '',
            'width': s.original_width, 'height': s.original_height,
            'stall_count': s.stalls.count(),
        } for s in sections]
        return render(request, 'portal/floor_plan.html', {
            'event': event, 'floor_plan': floor_plan,
            'stalls_data': json.dumps(stalls_data),
            'walkways_data': '[]', 'exits_data': '[]',
            'svg_content': '', 'zones': '[]',
            'svg_w': active_section.original_width if active_section else 1600,
            'svg_h': active_section.original_height if active_section else 900,
            'scale': 1,
            'sections': sections_data,
            'active_section': {
                'id': active_section.id,
                'name': active_section.name,
                'image_url': active_section.section_image.url if active_section.section_image else '',
                'width': active_section.original_width,
                'height': active_section.original_height,
                'scale_factor': active_section.scale_factor,
            },
        })

    stalls = event.stalls.all().select_related('zone')
    zones = list(event.zones.all().values('id', 'name', 'zone_type', 'color'))
    stalls_data = [{
        'id': s.id, 'name': s.name, 'x': s.position_x, 'y': s.position_y,
        'w': s.width, 'h': s.height, 'status': s.status,
        'price': float(s.total_price), 'is_corner': s.is_corner,
        'has_water': s.has_water, 'zone': s.zone_id,
        'size_sqm': float(s.size_sqm),
    } for s in stalls]
    walkways_raw = json.loads(floor_plan.walkways_json) if floor_plan and floor_plan.walkways_json else []
    exits_raw = json.loads(floor_plan.exit_markers_json) if floor_plan and floor_plan.exit_markers_json else []
    svg_content = ''
    fp_w, fp_h = 502485, 721189
    paths_to_try = ['floor_plans/dec_full_floor_plan.svg', 'dec_full_floor_plan.svg']
    raw = None
    for svg_rel_path in paths_to_try:
        if raw is not None:
            break
        try:
            from django.core.files.storage import default_storage
            if default_storage.exists(svg_rel_path):
                f = default_storage.open(svg_rel_path)
                raw = f.read()
                f.close()
                if isinstance(raw, bytes):
                    raw = raw.decode('utf-8', errors='replace')
        except Exception:
            pass
    if raw is None:
        for svg_rel_path in paths_to_try:
            full_svg = os.path.join(str(settings.MEDIA_ROOT), svg_rel_path)
            if os.path.exists(full_svg):
                with open(full_svg, 'r', encoding='utf-8') as f:
                    raw = f.read()
                break
    if raw:
        try:
            vb = re.search(r'viewBox="([^"]+)"', raw)
            if vb:
                parts = vb.group(1).split()
                fp_w = int(float(parts[2]))
                fp_h = int(float(parts[3]))
            raw = raw.replace('overflow="hidden"', 'overflow="visible"')
            svg_tag = re.search(r'<svg\b[^>]*>', raw)
            if svg_tag and 'overflow=' not in svg_tag.group():
                raw = raw[:svg_tag.end() - 1] + ' overflow="visible">' + raw[svg_tag.end():]
            raw = re.sub(r'<svg\b', '<svg class="fp-svg"', raw, count=1)
            raw = re.sub(r'width="[^"]*"', f'width="{fp_w}"', raw)
            raw = re.sub(r'height="[^"]*"', f'height="{fp_h}"', raw)
            svg_content = raw
        except Exception:
            pass

    return render(request, 'portal/floor_plan.html', {
        'event': event, 'floor_plan': floor_plan,
        'zones': json.dumps(zones), 'stalls_data': json.dumps(stalls_data),
        'walkways_data': json.dumps(walkways_raw),
        'exits_data': json.dumps(exits_raw),
        'svg_content': svg_content,
        'svg_w': fp_w,
        'svg_h': fp_h,
        'scale': 1,
        'sections': [],
        'active_section': None,
    })


@erp_section_required('floor_plan')
def floor_plan_frame(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    floor_plan = getattr(event, 'floor_plan', None)
    svg_content = ''
    fp_w, fp_h = 4000, 3000
    paths_to_try = ['floor_plans/dec_full_floor_plan.svg', 'dec_full_floor_plan.svg']
    raw = None
    for svg_rel_path in paths_to_try:
        if raw is not None:
            break
        try:
            from django.core.files.storage import default_storage
            print(f'frame SVG: trying storage path={svg_rel_path}, storage={type(default_storage).__name__}')
            if default_storage.exists(svg_rel_path):
                f = default_storage.open(svg_rel_path)
                raw = f.read()
                f.close()
                if isinstance(raw, bytes):
                    raw = raw.decode('utf-8', errors='replace')
                print(f'frame SVG: loaded from storage path={svg_rel_path}, size={len(raw)}')
        except Exception as e:
            print(f'frame SVG: storage failed for {svg_rel_path}: {e}')
    for svg_rel_path in paths_to_try:
        if raw is not None:
            break
        try:
            import requests as http_requests
            r2_domain = getattr(settings, 'AWS_S3_CUSTOM_DOMAIN', '')
            if r2_domain:
                url = f"https://{r2_domain}/{svg_rel_path}"
                print(f'frame SVG: trying public URL={url}')
                resp = http_requests.get(url, timeout=30)
                if resp.status_code == 200:
                    raw = resp.text
                    print(f'frame SVG: loaded from public URL, size={len(raw)}')
                else:
                    print(f'frame SVG: public URL returned {resp.status_code}')
        except Exception as e:
            print(f'frame SVG: public URL failed: {e}')
    if raw is None:
        for svg_rel_path in paths_to_try:
            full_svg = os.path.join(str(settings.MEDIA_ROOT), svg_rel_path)
            if os.path.exists(full_svg):
                with open(full_svg, 'r', encoding='utf-8') as f:
                    raw = f.read()
                print(f'frame SVG: loaded from local file={full_svg}')
                break
    if raw is None:
        print('frame SVG: all paths failed')
    if raw:
        try:
            vb = re.search(r'viewBox="([^"]+)"', raw)
            if vb:
                parts = vb.group(1).split()
                fp_w = int(float(parts[2]))
                fp_h = int(float(parts[3]))
            raw = raw.replace('overflow="hidden"', 'overflow="visible"')
            raw = raw.replace('<svg', '<svg class="fp-svg"')
            svg_content = raw
        except Exception:
            pass
    return render(request, 'portal/floor_plan_frame.html', {
        'floor_plan': floor_plan,
        'svg_content': svg_content,
        'svg_w': fp_w,
        'svg_h': fp_h,
    })


@erp_login_required
def upload_floor_plan(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    if request.method == 'POST':
        image = request.FILES.get('image')
        if image:
            FloorPlan.objects.update_or_create(event=event, defaults={'image': image})
            messages.success(request, 'Floor plan uploaded.')
        else:
            messages.error(request, 'No image selected.')
        return redirect('erp:event_detail', event_id=event_id)
    return redirect('erp:event_detail', event_id=event_id)


@erp_login_required
def create_stall(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    if request.method == 'POST':
        last = event.stalls.order_by('-id').first()
        num = (last.id % 100 + 1) if last else 1
        stall = Stall.objects.create(
            event=event,
            name=f"S{num:02d}",
            position_x=int(request.POST.get('x', 0)),
            position_y=int(request.POST.get('y', 0)),
            width=int(request.POST.get('width', 180)),
            height=int(request.POST.get('height', 180)),
            size_sqm=Decimal(request.POST.get('size_sqm', 9)),
            base_price=Decimal(request.POST.get('base_price', 5000)),
        )
        messages.success(request, f'Stall {stall.name} created.')
        return redirect('erp:event_detail', event_id=event_id)
    return redirect('erp:event_detail', event_id=event_id)


@erp_login_required
def save_floor_plan_meta(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    if request.method == 'POST':
        data = json.loads(request.body)
        floor_plan, _ = FloorPlan.objects.get_or_create(event=event)
        if 'walkways' in data:
            floor_plan.walkways_json = json.dumps(data['walkways'])
        if 'exits' in data:
            floor_plan.exit_markers_json = json.dumps(data['exits'])
        floor_plan.save()
        return JsonResponse({'ok': True})
    return JsonResponse({'ok': False}, status=405)


@erp_login_required
def save_stalls(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    if request.method == 'POST':
        data = json.loads(request.body)
        updated = 0
        created = 0
        for item in data:
            pk = item.get('id')
            stall = Stall.objects.filter(pk=pk, event=event).first() if pk else None
            if stall:
                stall.position_x = item['x']
                stall.position_y = item['y']
                stall.width = item['w']
                stall.height = item['h']
                stall.size_sqm = Decimal(str(item.get('size_sqm', stall.size_sqm)))
                stall.base_price = Decimal(str(item.get('base_price', stall.base_price)))
                stall.corner_premium = Decimal(str(item.get('corner_premium', '0')))
                stall.is_corner = item.get('is_corner', False)
                stall.has_water = item.get('has_water', False)
                stall.zone_id = item.get('zone')
                stall.save()
                updated += 1
            else:
                name = item.get('name', 'NEW')
                existing = Stall.objects.filter(event=event, name=name).first()
                if existing:
                    existing.position_x = item['x']
                    existing.position_y = item['y']
                    existing.width = item['w']
                    existing.height = item['h']
                    existing.size_sqm = Decimal(str(item.get('size_sqm', existing.size_sqm)))
                    existing.base_price = Decimal(str(item.get('base_price', existing.base_price)))
                    existing.corner_premium = Decimal(str(item.get('corner_premium', '0')))
                    existing.is_corner = item.get('is_corner', False)
                    existing.has_water = item.get('has_water', False)
                    existing.zone_id = item.get('zone')
                    existing.save()
                    updated += 1
                else:
                    prefix = item.get('prefix', 'S')
                    zone_id = item.get('zone')
                    Stall.objects.create(
                        event=event, name=name, stall_prefix=prefix,
                        position_x=item['x'], position_y=item['y'],
                        width=item['w'], height=item['h'],
                        size_sqm=Decimal(str(item.get('size_sqm', 9))),
                        base_price=Decimal(str(item.get('base_price', 5000))),
                        corner_premium=Decimal(str(item.get('corner_premium', '0'))),
                        is_corner=item.get('is_corner', False),
                        has_water=item.get('has_water', False),
                        zone_id=zone_id,
                    )
                    created += 1
        return JsonResponse({'ok': True, 'updated': updated, 'created': created})
    return JsonResponse({'ok': False}, status=405)


@erp_section_required('bookings')
def erp_booking_list(request):
    bookings = Booking.objects.all().select_related('exhibitor', 'event', 'stall')
    status = request.GET.get('status')
    q = request.GET.get('q', '').strip()
    if status:
        bookings = bookings.filter(status=status)
    if q:
        bookings = bookings.filter(
            Q(exhibitor__company_name__icontains=q) |
            Q(fascia_name__icontains=q) |
            Q(booking_reference__icontains=q) |
            Q(stall__name__icontains=q)
        )
    return render(request, 'portal/booking_list.html', {'bookings': bookings, 'q': q})


@erp_section_required('bookings')
def erp_booking_detail(request, pk):
    booking = get_object_or_404(Booking.objects.select_related('exhibitor', 'event', 'stall', 'stall__zone'), pk=pk)
    line = getattr(booking, 'invoice_line', None)
    invoices = [line.invoice] if line is not None else list(booking.invoices.all())
    inv = invoices[0] if invoices else None
    payments = inv.payments.all() if inv else booking.payments.all()
    discount_requests = booking.discount_requests.all()
    return render(request, 'portal/booking_detail.html', {
        'booking': booking, 'invoices': invoices,
        'payments': payments, 'discount_requests': discount_requests,
    })


@erp_login_required
def approve_booking(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    if booking.status == 'pending':
        booking.status = 'approved'
        booking.approved_date = timezone.now()
        booking.save()
        booking.stall.status = 'reserved'
        booking.stall.save()
        from invoices.views import ensure_booking_invoice
        inv, created = ensure_booking_invoice(booking)
        from invoices.models import LedgerEntry
        if not LedgerEntry.objects.filter(booking=booking, entry_type='invoice').exists():
            line = inv.invoice_lines.filter(booking=booking).first()
            amount = line.amount_incl if line is not None else booking.total_amount
            LedgerEntry.objects.create(
                exhibitor=booking.exhibitor, booking=booking,
                entry_type='invoice', description=f'Stall booking - {booking.stall.name}',
                reference=inv.invoice_number,
                debit=amount, credit=0, balance=inv.balance_due,
                entry_date=inv.issue_date,
            )
        if created:
            auto_post_invoice(inv, created_by=request.user)
        send_invoice_email(inv, 'created')
        messages.success(request, f'Booking {booking.booking_reference} approved. Invoice {inv.invoice_number} issued.')
    return redirect('erp:booking_detail', pk=pk)


@erp_login_required
def reject_booking(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    if booking.status == 'pending':
        booking.status = 'rejected'
        booking.save()
        booking.stall.status = 'available'
        booking.stall.save()
        messages.success(request, f'Booking {booking.booking_reference} rejected.')
    return redirect('erp:booking_detail', pk=pk)


@erp_login_required
def confirm_booking(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    if booking.status == 'approved':
        booking.status = 'confirmed'
        booking.confirmed_date = timezone.now()
        booking.payment_status = 'paid'
        booking.save()
        booking.stall.status = 'confirmed'
        booking.stall.save()
        messages.success(request, f'Booking {booking.booking_reference} confirmed.')
        send_booking_confirmation(booking)
    return redirect('erp:booking_detail', pk=pk)


@erp_section_required('invoices')
def erp_invoice_list(request):
    q = request.GET.get('q', '').strip()
    invoices = Invoice.objects.all().select_related('exhibitor', 'event', 'booking', 'booking__stall')
    if q:
        invoices = invoices.filter(
            Q(exhibitor__company_name__icontains=q) |
            Q(invoice_number__icontains=q) |
            Q(booking__booking_reference__icontains=q) |
            Q(booking__fascia_name__icontains=q) |
            Q(invoice_lines__booking__stall__name__icontains=q) |
            Q(invoice_lines__booking__booking_reference__icontains=q)
        ).distinct()
    return render(request, 'portal/invoice_list.html', {'invoices': invoices, 'q': q})


@erp_section_required('invoices')
def erp_invoice_detail(request, pk):
    invoice = get_object_or_404(
        Invoice.objects.select_related('exhibitor', 'event').prefetch_related(
            'invoice_lines__booking__stall', 'invoice_lines__booking__event'
        ),
        pk=pk,
    )
    from invoices.views import refresh_invoice
    refresh_invoice(invoice)
    invoice.refresh_from_db()
    booking = invoice.display_booking
    payments = invoice.payments.all().select_related('invoice').order_by('payment_date')
    lines = invoice.invoice_lines.all()
    verified_total = payments.filter(status='verified').aggregate(s=Sum('amount'))['s'] or Decimal('0')
    return render(request, 'portal/invoice_detail.html', {
        'invoice': invoice, 'booking': booking,
        'payments': payments, 'verified_total': verified_total, 'lines': lines,
    })


@erp_login_required
def create_invoice(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id)
    if request.method == 'POST':
        from invoices.views import ensure_booking_invoice
        inv, created = ensure_booking_invoice(booking)
        from invoices.models import LedgerEntry
        if not LedgerEntry.objects.filter(booking=booking, entry_type='invoice').exists():
            line = inv.invoice_lines.filter(booking=booking).first()
            amount = line.amount_incl if line is not None else booking.total_amount
            LedgerEntry.objects.create(
                exhibitor=booking.exhibitor, booking=booking,
                entry_type='invoice', description=f'Stall booking - {booking.stall.name}',
                reference=inv.invoice_number,
                debit=amount, credit=0, balance=inv.balance_due,
                entry_date=inv.issue_date,
            )
        if created:
            auto_post_invoice(inv, created_by=request.user)
        send_invoice_email(inv, 'created')
        messages.success(request, f'Invoice {inv.invoice_number} updated.')
        return redirect('erp:booking_detail', pk=booking_id)
    return redirect('erp:booking_detail', pk=booking_id)


@erp_section_required('payments')
def erp_payment_list(request):
    payments = Payment.objects.all().select_related('invoice', 'invoice__exhibitor', 'booking')
    status = request.GET.get('status')
    q = request.GET.get('q', '').strip()
    if status:
        payments = payments.filter(status=status)
    if q:
        payments = payments.filter(
            Q(invoice__exhibitor__company_name__icontains=q) |
            Q(booking__fascia_name__icontains=q) |
            Q(invoice__invoice_number__icontains=q) |
            Q(reference_number__icontains=q) |
            Q(booking__stall__name__icontains=q)
        )
    return render(request, 'portal/payment_list.html', {'payments': payments, 'q': q})


@erp_login_required
def verify_payment(request, pk):
    payment = get_object_or_404(Payment, pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action', 'verify')
        if action == 'verify':
            payment.status = 'verified'
            payment.verified_by = request.user
            payment.verified_at = timezone.now()
            payment.receipt_number = f"RCT-{uuid.uuid4().hex[:8].upper()}"
            payment.save()
            inv = payment.invoice
            from invoices.views import refresh_invoice
            refresh_invoice(inv)
            exhibitor = payment.invoice.exhibitor or (payment.booking.exhibitor if payment.booking else None)
            booking = inv.display_booking
            receipt = Receipt.objects.create(
                receipt_number=payment.receipt_number,
                payment=payment,
                exhibitor=exhibitor,
                amount=payment.amount,
                payment_method=payment.payment_method,
                reference_number=payment.reference_number,
                issue_date=timezone.now().date(),
            )
            if booking is not None:
                LedgerEntry.objects.create(
                    exhibitor=exhibitor,
                    booking=booking,
                    entry_type='payment',
                    description=f'Payment received - {inv.invoice_number}',
                    reference=receipt.receipt_number,
                    debit=0, credit=payment.amount,
                    balance=inv.balance_due,
                    entry_date=timezone.now().date(),
                )
            auto_post_payment(payment, created_by=request.user)
            from notifications.utils import send_payment_verified
            send_payment_verified(payment, receipt)
            messages.success(request, f'Payment verified. Receipt: {receipt.receipt_number}.')
        elif action == 'reject':
            payment.status = 'rejected'
            payment.save()
            messages.warning(request, 'Payment rejected.')
    return redirect('erp:payment_list')


@erp_section_required('payments')
def collect_cash(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id)
    line = getattr(booking, 'invoice_line', None)
    invoice = line.invoice if line is not None else booking.invoices.first()
    if not invoice:
        messages.error(request, 'No invoice found for this booking.')
        return redirect('erp:booking_detail', pk=booking_id)
    if request.method == 'POST':
        amount = Decimal(request.POST.get('amount', '0'))
        ref = request.POST.get('reference_number', booking.stall.name)
        notes = request.POST.get('notes', '')
        if amount <= 0:
            messages.error(request, 'Amount must be greater than zero.')
            return redirect('erp:collect_cash', booking_id=booking_id)
        from invoices.models import InvoiceLine
        line = InvoiceLine.objects.filter(booking=booking).first()
        inv = line.invoice if line else booking.invoices.first()
        payment = Payment.objects.create(
            invoice=invoice,
            booking=booking,
            amount=amount,
            payment_method='cash',
            reference_number=ref,
            status='verified',
            verified_by=request.user,
            verified_at=timezone.now(),
            notes=notes,
        )
        payment.receipt_number = f"RCT-{uuid.uuid4().hex[:8].upper()}"
        payment.save()
        from invoices.views import refresh_invoice
        refresh_invoice(inv)
        receipt = Receipt.objects.create(
            receipt_number=payment.receipt_number,
            payment=payment,
            exhibitor=inv.exhibitor,
            amount=payment.amount,
            payment_method='cash',
            reference_number=ref,
            issue_date=timezone.now().date(),
            notes=notes,
        )
        auth_booking = inv.display_booking
        if auth_booking is not None:
            LedgerEntry.objects.create(
                exhibitor=inv.exhibitor,
                booking=auth_booking,
                entry_type='payment',
                description=f'Cash payment - {invoice.invoice_number}',
                reference=receipt.receipt_number,
                debit=0, credit=payment.amount,
                balance=inv.balance_due,
                entry_date=timezone.now().date(),
            )
        auto_post_payment(payment, created_by=request.user)
        send_payment_verified_email(payment, receipt)
        messages.success(request, f'Cash payment of R{amount:.2f} recorded. Receipt: {receipt.receipt_number}')
        return redirect('erp:booking_detail', pk=booking_id)
    from invoices.views import refresh_invoice as _rf
    _rf(invoice)
    invoice.refresh_from_db()
    verified_total = invoice.payments.filter(status='verified').aggregate(s=Sum('amount'))['s'] or Decimal('0')
    context = {
        'booking': booking,
        'invoice': invoice,
        'balance_due': invoice.balance_due,
        'verified_total': invoice.amount_paid,
    }
    return render(request, 'portal/collect_cash.html', context)


@erp_section_required('payments')
def print_payments_receipt(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id)
    line = getattr(booking, 'invoice_line', None)
    invoice = line.invoice if line is not None else booking.invoices.first()
    payments = Payment.objects.filter(
        invoice=invoice, status='verified'
    ).select_related('invoice').order_by('payment_date') if invoice else Payment.objects.none()
    receipt = None
    if payments.exists():
        last_payment = payments.first()
        receipt = Receipt.objects.filter(payment=last_payment).first()
    total_paid = payments.aggregate(s=Sum('amount'))['s'] or Decimal('0')
    return render(request, 'printouts/payments_receipt.html', {
        'booking': booking,
        'invoice': invoice,
        'payments': payments,
        'receipt': receipt,
        'total_paid': total_paid,
    })


@erp_section_required('exhibitors')
def erp_exhibitor_list(request):
    exhibitors = User.objects.filter(user_type='exhibitor')
    q = request.GET.get('q')
    if q:
        exhibitors = exhibitors.filter(Q(company_name__icontains=q) | Q(email__icontains=q) | Q(username__icontains=q))
    return render(request, 'portal/exhibitor_list.html', {'exhibitors': exhibitors})


@erp_login_required
def erp_accessory_list(request):
    accessories = AccessoryType.objects.all()
    return render(request, 'portal/accessory_list.html', {'accessories': accessories})


@erp_login_required
def add_accessory(request):
    if request.method == 'POST':
        AccessoryType.objects.create(
            name=request.POST['name'],
            description=request.POST.get('description', ''),
            price=Decimal(request.POST['price']),
            unit=request.POST.get('unit', 'per unit'),
        )
        messages.success(request, 'Accessory added.')
    return redirect('erp:accessory_list')


@erp_login_required
def erp_discount_list(request):
    discounts = DiscountRequest.objects.all().select_related('booking', 'requested_by')
    return render(request, 'portal/discount_list.html', {'discounts': discounts})


@erp_login_required
def approve_discount(request, pk):
    dr = get_object_or_404(DiscountRequest, pk=pk)
    if dr.status == 'pending':
        dr.approved_by_first = request.user
        dr.status = 'approved_by_first'
        dr.save()
        # Notify remaining directors that first approval was given
        from notifications.utils import get_director_emails, send_html_email
        remaining = [e for e in get_director_emails() if e != request.user.email]
        if remaining:
            context = {
                'dr': dr,
                'booking': dr.booking,
                'approved_by': request.user,
                'site_name': settings.SITE_NAME,
                'site_url': settings.SITE_URL,
            }
            send_html_email(
                f'First Approval Received - {dr.discount_percent}% - {dr.booking.booking_reference}',
                'emails/discount_first_approval.html', context, remaining,
            )
        messages.success(request, f'Discount request approved by {request.user.username} (1/2). Awaiting second approval.')
    elif dr.status == 'approved_by_first':
        dr.approved_by_second = request.user
        dr.status = 'approved'
        dr.booking.subtotal -= dr.discount_amount
        from bookings.pricing import embedded_vat
        rate = float(dr.booking.event.vat_rate) / 100
        dr.booking.vat_amount = embedded_vat(dr.booking.subtotal - dr.booking.electricity_deposit, rate=rate)
        dr.booking.total_amount = dr.booking.subtotal
        dr.booking.balance_due = dr.booking.total_amount - dr.booking.amount_paid
        dr.booking.save()
        dr.save()
        # Update the booking's consolidated invoice line
        line = getattr(dr.booking, 'invoice_line', None)
        if line is not None:
            from invoices.views import update_invoice_from_booking
            update_invoice_from_booking(dr.booking)
            # Create credit note ledger entry for the discount
            from invoices.models import LedgerEntry
            LedgerEntry.objects.create(
                exhibitor=dr.booking.exhibitor,
                booking=dr.booking,
                entry_type='credit',
                description=f'Discount {dr.discount_percent}% approved - {dr.booking.booking_reference}',
                reference=f'DISC-{dr.pk}',
                debit=0,
                credit=dr.discount_amount,
                balance=inv.balance_due,
                entry_date=timezone.now().date(),
            )
        # Auto-post accounting adjustment
        from accounting.auto_post import auto_post_discount
        auto_post_discount(dr.booking, dr.discount_amount, request.user)
        send_discount_decision(dr)
        messages.success(request, f'Discount fully approved by {request.user.username} (2/2). Totals updated.')
    return redirect('erp:discount_list')


@erp_login_required
def reject_discount(request, pk):
    dr = get_object_or_404(DiscountRequest, pk=pk)
    if dr.status in ['pending', 'approved_by_first']:
        dr.status = 'rejected'
        dr.rejected_by = request.user
        dr.save()
        send_discount_decision(dr)
        messages.success(request, f'Discount request rejected by {request.user.username}.')
    return redirect('erp:discount_list')


@erp_login_required
def print_stand_spec(request, booking_id):
    booking = get_object_or_404(Booking.objects.select_related('exhibitor', 'event', 'stall', 'stall__zone'), pk=booking_id)
    return render(request, 'printouts/stand_spec.html', {'booking': booking})


@erp_login_required
def print_electrician(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    if request.method == 'POST':
        pk = request.POST.get('booking_id')
        action = request.POST.get('action')
        if pk and action:
            b = get_object_or_404(Booking, pk=pk)
            if action == 'complete_electrical':
                b.electrical_completed = True
                b.save()
                messages.success(request, f'{b.booking_reference} marked electrical complete.')
            elif action == 'reset_electrical':
                b.electrical_completed = False
                b.save()
                messages.success(request, f'{b.booking_reference} electrical reset.')
        return redirect('erp:print_electrician', event_id=event_id)
    bookings = event.bookings.all().select_related('stall', 'exhibitor').prefetch_related('accessories__accessory')
    return render(request, 'printouts/electrician.html', {'event': event, 'bookings': bookings})


@erp_login_required
def print_stand_builder(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    if request.method == 'POST':
        pk = request.POST.get('booking_id')
        action = request.POST.get('action')
        if pk and action:
            b = get_object_or_404(Booking, pk=pk)
            if action == 'complete_build':
                b.stand_build_completed = True
                b.save()
                messages.success(request, f'{b.booking_reference} marked build complete.')
            elif action == 'reset_build':
                b.stand_build_completed = False
                b.save()
                messages.success(request, f'{b.booking_reference} build reset.')
        return redirect('erp:print_stand_builder', event_id=event_id)
    bookings = event.bookings.all().select_related('stall__zone', 'exhibitor')
    total_tables = sum(b.stall.num_tables for b in bookings if b.stall)
    total_chairs = sum(b.stall.num_chairs for b in bookings if b.stall)
    return render(request, 'printouts/stand_builder.html', {
        'event': event, 'bookings': bookings,
        'total_tables': total_tables, 'total_chairs': total_chairs,
    })


@erp_login_required
def print_accessories(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    bookings = event.bookings.all().prefetch_related('accessories__accessory', 'stall')
    return render(request, 'printouts/accessories.html', {'event': event, 'bookings': bookings})


@erp_section_required('accounting')
def erp_statement(request, exhibitor_id):
    exhibitor = get_object_or_404(User, pk=exhibitor_id, user_type='exhibitor')
    entries = LedgerEntry.objects.filter(exhibitor=exhibitor).select_related('booking', 'booking__stall').order_by('entry_date', 'created_at')
    from invoices.views import refresh_invoice
    invoices = Invoice.objects.filter(exhibitor=exhibitor).order_by('issue_date')
    rows = []
    stand_balances = []
    total_invoiced = Decimal('0')
    total_paid = Decimal('0')
    for inv in invoices:
        refresh_invoice(inv)
        inv.refresh_from_db()
        lines = list(inv.invoice_lines.select_related('booking__stall', 'booking__event'))
        total_invoiced += inv.amount_incl
        total_paid += inv.amount_paid
        rows.append({
            'invoice': inv,
            'lines': lines,
            'total': inv.amount_incl,
            'paid': inv.amount_paid,
            'balance': inv.balance_due,
        })
        for l in lines:
            b = l.booking
            stand_balances.append({
                'booking': b,
                'stall_name': b.stall.name if b.stall else '-',
                'fascia_name': b.fascia_name or '-',
                'event_name': b.event.name if b.event else '-',
                'total': l.amount_incl,
                'paid': b.amount_paid,
                'balance': b.balance_due,
            })
    outstanding = total_invoiced - total_paid
    total_debits = entries.aggregate(s=Sum('debit'))['s'] or Decimal('0')
    total_credits = entries.aggregate(s=Sum('credit'))['s'] or Decimal('0')
    today = timezone.localdate()
    aging_current = aging_30 = aging_60 = aging_90 = Decimal('0')
    for inv in Invoice.objects.filter(exhibitor=exhibitor, status__in=['sent', 'partial', 'overdue']):
        bal = inv.balance_due
        if bal > 0:
            days = (today - inv.due_date).days
            if days <= 0: aging_current += bal
            elif days <= 30: aging_30 += bal
            elif days <= 60: aging_60 += bal
            else: aging_90 += bal
    total_debits = total_invoiced
    total_credits = total_paid
    closing_balance = total_debits - total_credits
    return render(request, 'printouts/statement.html', {
        'exhibitor': exhibitor, 'ledger': entries, 'invoice_rows': rows,
        'total_invoiced': total_invoiced, 'total_paid': total_paid,
        'outstanding': outstanding, 'overdue': aging_30 + aging_60 + aging_90,
        'total_debits': total_debits, 'total_credits': total_credits,
        'closing_balance': closing_balance,
        'aging_current': aging_current, 'aging_30': aging_30,
        'aging_60': aging_60, 'aging_90': aging_90,
        'stand_balances': stand_balances,
    })


@erp_section_required('reports')
def erp_reports(request):
    events = Event.objects.all()
    report_data = []
    for event in events:
        total_bookings = event.bookings.count()
        confirmed = event.bookings.filter(status='confirmed').count()
        total_rev = event.bookings.aggregate(s=Sum('total_amount'))['s'] or 0
        paid_rev = event.bookings.filter(payment_status='paid').aggregate(s=Sum('total_amount'))['s'] or 0
        report_data.append({
            'event': event,
            'total_bookings': total_bookings,
            'confirmed': confirmed,
            'total_revenue': total_rev,
            'paid_revenue': paid_rev,
            'outstanding': total_rev - paid_rev,
        })
    return render(request, 'portal/reports.html', {'report_data': report_data})


def build_section_summary(event):
    """Per-floor-plan-section summary for the consolidated bookings report."""
    from django.db.models import F, Prefetch
    if not event:
        return []
    sections = list(event.floor_plan_sections.all().order_by('display_order', 'name'))
    sold_statuses = ['pending', 'approved', 'confirmed', 'completed']
    summary = []
    for sec in sections:
        total_stalls = event.stalls.filter(section=sec).count()
        sold_qs = Booking.objects.filter(event=event, stall__section=sec, status__in=sold_statuses)
        stalls_sold = sold_qs.count()
        sales_amount = sold_qs.aggregate(s=Sum('stall_price'))['s'] or Decimal('0')
        revenue = sold_qs.aggregate(s=Sum('total_amount'))['s'] or Decimal('0')
        discounts = Decimal('0')
        for bk in sold_qs.prefetch_related('discount_requests'):
            for d in bk.discount_requests.filter(status='approved'):
                discounts += d.discount_amount
        avail_qs = event.stalls.filter(section=sec, status='available')
        stalls_available = avail_qs.count()
        unsold_row = avail_qs.annotate(
            v=F('base_price') + F('corner_premium') + F('entrance_premium')
        ).aggregate(s=Sum('v'))['s'] or Decimal('0')
        summary.append({
            'section': sec,
            'total_stalls': total_stalls,
            'stalls_sold': stalls_sold,
            'stalls_available': stalls_available,
            'stalls_held': total_stalls - stalls_sold - stalls_available,
            'sales_amount': sales_amount,
            'unsold_amount': unsold_row,
            'discounts': discounts,
            'revenue': revenue,
            'outstanding': sold_qs.aggregate(s=Sum('balance_due'))['s'] or Decimal('0'),
            'received': sold_qs.aggregate(s=Sum('amount_paid'))['s'] or Decimal('0'),
        })
    grand = {
        'total_stalls': sum(r['total_stalls'] for r in summary),
        'stalls_sold': sum(r['stalls_sold'] for r in summary),
        'stalls_available': sum(r['stalls_available'] for r in summary),
        'stalls_held': sum(r['stalls_held'] for r in summary),
        'sales_amount': sum(r['sales_amount'] for r in summary),
        'unsold_amount': sum(r['unsold_amount'] for r in summary),
        'discounts': sum(r['discounts'] for r in summary),
        'revenue': sum(r['revenue'] for r in summary),
        'outstanding': sum(r['outstanding'] for r in summary),
        'received': sum(r['received'] for r in summary),
    }
    return {'sections': summary, 'grand': grand}


@erp_section_required('booking_reports')
def erp_consolidated_bookings_report(request):
    from django.db.models import Prefetch
    from django.core.exceptions import ObjectDoesNotExist

    events = Event.objects.order_by('start_date')
    active_event = events.first()
    event_id = request.GET.get('event_id')
    section_id = request.GET.get('section_id', '')
    if event_id:
        active_event = events.filter(pk=event_id).first() or active_event
    if not active_event:
        return render(request, 'portal/consolidated_bookings_report.html', {
            'events': [], 'sections': [], 'active_event': None,
            'active_section': None, 'all_sections': True, 'rows': [],
            'totals': None,
        })

    sections = list(active_event.floor_plan_sections.all().order_by('display_order', 'name'))
    active_section = None
    all_sections = section_id == '' or section_id == 'all'
    if not all_sections:
        try:
            active_section = next((s for s in sections if str(s.pk) == str(section_id)), None)
        except (ObjectDoesNotExist, ValueError):
            active_section = None
        if active_section is None:
            all_sections = True

    base_qs = Booking.objects.filter(event=active_event)
    if not all_sections:
        base_qs = base_qs.filter(stall__section=active_section)

    base_qs = base_qs.select_related('exhibitor', 'stall', 'stall__zone').prefetch_related(
        'discount_requests',
        Prefetch('payments', queryset=Payment.objects.filter(status='verified').order_by('payment_date'), to_attr='verified_payments'),
    )

    rows = []
    totals = {
        'count': 0,
        'stall_price': Decimal('0'),
        'extras': Decimal('0'),
        'elec': Decimal('0'),
        'discount': Decimal('0'),
        'due': Decimal('0'),
        'paid1': Decimal('0'),
        'paid2': Decimal('0'),
        'paid': Decimal('0'),
        'balance': Decimal('0'),
    }
    for bk in base_qs:
        stall = bk.stall
        pay1 = pay2 = Decimal('0')
        pay_type = '-'
        pays = getattr(bk, 'verified_payments', [])
        if pays:
            pay1 = pays[0].amount
            pay_type = pays[0].get_payment_method_display()
        if len(pays) >= 2:
            pay2 = pays[1].amount
        discount = sum((d.discount_amount for d in bk.discount_requests.filter(status='approved')), Decimal('0'))
        size = f"{(Decimal(stall.width or 0) / 1000).quantize(Decimal('0.1'))}x{(Decimal(stall.height or 0) / 1000).quantize(Decimal('0.1'))}" if stall else ''
        due = bk.total_amount
        pct = (bk.balance_due / due * 100).quantize(Decimal('0.01')) if due else Decimal('0')
        rows.append({
            'booking': bk,
            'exhibitor': bk.exhibitor.company_name or bk.exhibitor.get_full_name() or bk.exhibitor.username,
            'stall_name': stall.name if stall else '-',
            'section_name': (stall.section.name if stall and stall.section else '-'),
            'size': size,
            'description': (stall.zone.name if stall and stall.zone else '-'),
            'stall_price': bk.stall_price,
            'extras': bk.accessories_total,
            'elec': bk.electricity_deposit,
            'discount': discount,
            'due': due,
            'pay_type': pay_type,
            'pay1': pay1,
            'pay2': pay2,
            'paid': bk.amount_paid,
            'balance': bk.balance_due,
            'pct': pct,
            'status': bk.get_payment_status_display(),
        })
        totals['count'] += 1
        totals['stall_price'] += bk.stall_price
        totals['extras'] += bk.accessories_total
        totals['elec'] += bk.electricity_deposit
        totals['discount'] += discount
        totals['due'] += due
        totals['paid1'] += pay1
        totals['paid2'] += pay2
        totals['paid'] += bk.amount_paid
        totals['balance'] += bk.balance_due
    totals['pct'] = (totals['balance'] / totals['due'] * 100).quantize(Decimal('0.01')) if totals['due'] else Decimal('0')

    return render(request, 'portal/consolidated_bookings_report.html', {
        'events': events,
        'sections': sections,
        'active_event': active_event,
        'active_section': active_section if not all_sections else None,
        'all_sections': all_sections,
        'rows': rows,
        'totals': totals,
        'section_summary': build_section_summary(active_event),
    })


@erp_section_required('expenses')
def erp_expense_list(request):
    expenses = Expense.objects.all().select_related('provider', 'created_by')
    status = request.GET.get('status')
    if status:
        expenses = expenses.filter(status=status)
    return render(request, 'portal/expense_list.html', {'expenses': expenses})


@erp_login_required
def erp_expense_create(request):
    providers = ServiceProvider.objects.filter(is_active=True)
    if request.method == 'POST':
        from decimal import Decimal
        provider_id = request.POST.get('provider')
        provider = get_object_or_404(ServiceProvider, pk=provider_id) if provider_id else None
        excl = Decimal(request.POST.get('amount_excl', '0'))
        vat = excl * Decimal('0.15')
        incl = excl + vat
        expense = Expense.objects.create(
            provider=provider,
            description=request.POST.get('description', ''),
            category=request.POST.get('category', 'other'),
            amount_excl=excl,
            vat_amount=vat,
            amount_incl=incl,
            balance_due=incl,
            expense_date=timezone.now().date(),
            due_date=request.POST.get('due_date') or None,
            notes=request.POST.get('notes', ''),
            created_by=request.user,
        )
        from accounting.auto_post import auto_post_expense
        auto_post_expense(expense, created_by=request.user)
        messages.success(request, f'Expense created: {expense.description[:50]}')
        return redirect('erp:expense_list')
    return render(request, 'portal/expense_form.html', {'providers': providers, 'edit': False})


@erp_login_required
def erp_expense_edit(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    providers = ServiceProvider.objects.filter(is_active=True)
    if request.method == 'POST':
        from decimal import Decimal
        provider_id = request.POST.get('provider')
        expense.provider = get_object_or_404(ServiceProvider, pk=provider_id) if provider_id else None
        expense.description = request.POST.get('description', '')
        expense.category = request.POST.get('category', 'other')
        expense.notes = request.POST.get('notes', '')
        expense.save()
        messages.success(request, 'Expense updated.')
        return redirect('erp:expense_list')
    return render(request, 'portal/expense_form.html', {'expense': expense, 'providers': providers, 'edit': True})


@erp_login_required
def erp_expense_pay(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    if request.method == 'POST':
        from decimal import Decimal
        amount = Decimal(request.POST.get('amount', '0'))
        expense.amount_paid += amount
        expense.balance_due = expense.amount_incl - expense.amount_paid
        expense.payment_reference = request.POST.get('payment_reference', '')
        if expense.balance_due <= 0:
            expense.status = 'paid'
            expense.paid_date = timezone.now().date()
        elif expense.amount_paid > 0:
            expense.status = 'partial'
        expense.save()
        from accounting.auto_post import auto_post_expense_payment
        auto_post_expense_payment(expense, amount, created_by=request.user)
        messages.success(request, f'Payment of R{amount:.2f} recorded for expense.')
        return redirect('erp:expense_list')
    return render(request, 'portal/expense_pay.html', {'expense': expense})


@erp_login_required
def erp_provider_ledger(request, pk):
    """Show a provider's full ledger: expenses (liability) + payments made."""
    provider = get_object_or_404(ServiceProvider, pk=pk)
    expenses = Expense.objects.filter(provider=provider).order_by('expense_date')
    total_billed = sum(e.amount_incl for e in expenses)
    total_paid = sum(e.amount_paid for e in expenses)
    balance_due = total_billed - total_paid
    return render(request, 'portal/provider_ledger.html', {
        'provider': provider,
        'expenses': expenses,
        'total_billed': total_billed,
        'total_paid': total_paid,
        'balance_due': balance_due,
    })


@erp_section_required('providers')
def erp_provider_list(request):
    providers = ServiceProvider.objects.all()
    q = request.GET.get('q')
    if q:
        providers = providers.filter(Q(company_name__icontains=q) | Q(contact_person__icontains=q))
    return render(request, 'portal/provider_list.html', {'providers': providers})


@erp_login_required
def erp_provider_create(request):
    if request.method == 'POST':
        from django.contrib.auth.hashers import make_password
        import uuid
        email = request.POST.get('email', '')
        manual_pwd = request.POST.get('password', '').strip()
        pwd = manual_pwd if manual_pwd else str(uuid.uuid4().hex[:12])
        provider = ServiceProvider.objects.create(
            email=email,
            password=make_password(pwd),
            company_name=request.POST.get('company_name', ''),
            company_type=request.POST.get('company_type', 'ptyltd'),
            registration_number=request.POST.get('registration_number', ''),
            vat_number=request.POST.get('vat_number', ''),
            service_type=request.POST.get('service_type', 'other'),
            phone=request.POST.get('phone', ''),
            alternative_phone=request.POST.get('alternative_phone', ''),
            contact_person=request.POST.get('contact_person', ''),
            physical_address=request.POST.get('physical_address', ''),
            postal_address=request.POST.get('postal_address', ''),
            bank_name=request.POST.get('bank_name', ''),
            bank_branch=request.POST.get('bank_branch', ''),
            bank_account_number=request.POST.get('bank_account_number', ''),
            bank_account_type=request.POST.get('bank_account_type', 'business'),
            bank_branch_code=request.POST.get('bank_branch_code', ''),
        )
        msg = f'Provider {provider.company_name} created.'
        if not manual_pwd:
            msg += f' Auto-generated password: {pwd}'
        messages.success(request, msg)
        return redirect('erp:provider_list')
    return render(request, 'portal/provider_form.html', {'edit': False})


@erp_login_required
def erp_provider_edit(request, pk):
    provider = get_object_or_404(ServiceProvider, pk=pk)
    if request.method == 'POST':
        from django.contrib.auth.hashers import make_password
        provider.company_name = request.POST.get('company_name', '')
        provider.company_type = request.POST.get('company_type', 'ptyltd')
        provider.registration_number = request.POST.get('registration_number', '')
        provider.vat_number = request.POST.get('vat_number', '')
        provider.service_type = request.POST.get('service_type', 'other')
        provider.phone = request.POST.get('phone', '')
        provider.alternative_phone = request.POST.get('alternative_phone', '')
        provider.contact_person = request.POST.get('contact_person', '')
        provider.physical_address = request.POST.get('physical_address', '')
        provider.postal_address = request.POST.get('postal_address', '')
        provider.bank_name = request.POST.get('bank_name', '')
        provider.bank_branch = request.POST.get('bank_branch', '')
        provider.bank_account_number = request.POST.get('bank_account_number', '')
        provider.bank_account_type = request.POST.get('bank_account_type', 'business')
        provider.bank_branch_code = request.POST.get('bank_branch_code', '')
        provider.is_verified = request.POST.get('is_verified') == 'on'
        new_pwd = request.POST.get('new_password', '').strip()
        if new_pwd:
            provider.password = make_password(new_pwd)
        provider.save()
        msg = 'Provider updated.'
        if new_pwd:
            msg += f' New password set.'
        messages.success(request, msg)
        return redirect('erp:provider_detail', pk=provider.pk)
    return render(request, 'portal/provider_form.html', {'provider': provider, 'edit': True})


@erp_login_required
def erp_provider_detail(request, pk):
    provider = get_object_or_404(ServiceProvider, pk=pk)
    logs = provider.service_logs.all()
    expenses = provider.expenses.all()
    return render(request, 'portal/provider_detail.html', {
        'provider': provider, 'logs': logs, 'expenses': expenses,
    })


@erp_login_required
def erp_provider_add_log(request, pk):
    provider = get_object_or_404(ServiceProvider, pk=pk)
    if request.method == 'POST':
        from decimal import Decimal
        ServiceLog.objects.create(
            provider=provider,
            event_id=request.POST.get('event_id') or None,
            description=request.POST.get('description', ''),
            service_date=request.POST.get('service_date') or timezone.now().date(),
            amount_charged=Decimal(request.POST.get('amount_charged', '0')),
            notes=request.POST.get('notes', ''),
        )
        messages.success(request, 'Service log added.')
        return redirect('erp:provider_detail', pk=pk)
    from events.models import Event
    events = Event.objects.all()
    return render(request, 'portal/provider_log_form.html', {'provider': provider, 'events': events})


@erp_section_required('users')
def erp_user_list(request):
    users = User.objects.all().select_related('role')
    q = request.GET.get('q')
    ut = request.GET.get('user_type')
    if q:
        users = users.filter(Q(username__icontains=q) | Q(email__icontains=q) | Q(company_name__icontains=q))
    if ut:
        users = users.filter(user_type=ut)
    return render(request, 'portal/user_list.html', {'users': users, 'user_types': User.USER_TYPES})


@erp_login_required
def erp_user_create(request):
    roles = Role.objects.filter(is_active=True)
    if request.method == 'POST':
        utype = request.POST.get('user_type', 'staff')
        is_staff_val = utype in ('staff', 'finance', 'director', 'admin', 'superadmin')
        user = User.objects.create_user(
            username=request.POST.get('username', ''),
            email=request.POST.get('email', ''),
            password=request.POST.get('password', 'changeme123'),
            user_type=utype,
            phone=request.POST.get('phone', ''),
            company_name=request.POST.get('company_name', ''),
            is_staff=is_staff_val,
            role_id=request.POST.get('role_id') or None,
        )
        messages.success(request, f'User {user.username} created.')
        return redirect('erp:user_list')
    return render(request, 'portal/user_form.html', {'roles': roles, 'edit': False})


@erp_login_required
def erp_user_edit(request, pk):
    user = get_object_or_404(User, pk=pk)
    roles = Role.objects.filter(is_active=True)
    if request.method == 'POST':
        utype = request.POST.get('user_type', 'staff')
        user.username = request.POST.get('username', user.username)
        user.email = request.POST.get('email', '')
        user.first_name = request.POST.get('first_name', '')
        user.last_name = request.POST.get('last_name', '')
        user.user_type = utype
        user.is_staff = utype in ('staff', 'finance', 'director', 'admin', 'superadmin')
        user.phone = request.POST.get('phone', '')
        user.company_name = request.POST.get('company_name', '')
        user.is_active = request.POST.get('is_active') == 'on'
        user.role_id = request.POST.get('role_id') or None
        pwd = request.POST.get('password', '')
        if pwd:
            user.set_password(pwd)
        user.save()
        messages.success(request, f'User {user.username} updated.')
        return redirect('erp:user_list')
    return render(request, 'portal/user_form.html', {'edit_user': user, 'roles': roles, 'edit': True})


@erp_login_required
@user_passes_test(is_admin_user)
def erp_role_list(request):
    roles = Role.objects.all().prefetch_related('permissions')
    return render(request, 'portal/role_list.html', {'roles': roles})


@erp_login_required
@user_passes_test(is_admin_user)
def erp_role_create(request):
    if request.method == 'POST':
        role = Role.objects.create(
            name=request.POST.get('name', ''),
            description=request.POST.get('description', ''),
        )
        # Create default permissions for all sections
        for section, _ in RolePermission.SECTIONS:
            RolePermission.objects.create(
                role=role, section=section,
                can_view=True, can_create=False,
                can_edit=False, can_delete=False,
            )
        messages.success(request, f'Role {role.name} created. Configure permissions below.')
        return redirect('erp:role_edit', pk=role.pk)
    return render(request, 'portal/role_form.html', {'edit': False})


@erp_login_required
@user_passes_test(is_admin_user)
def erp_role_edit(request, pk):
    role = get_object_or_404(Role, pk=pk)
    if request.method == 'POST':
        role.name = request.POST.get('name', '')
        role.description = request.POST.get('description', '')
        role.save()
        # Update permissions
        for section, _ in RolePermission.SECTIONS:
            perm, _ = RolePermission.objects.get_or_create(role=role, section=section)
            perm.can_view = request.POST.get(f'perm_{section}_view') == 'on'
            perm.can_create = request.POST.get(f'perm_{section}_create') == 'on'
            perm.can_edit = request.POST.get(f'perm_{section}_edit') == 'on'
            perm.can_delete = request.POST.get(f'perm_{section}_delete') == 'on'
            perm.save()
        messages.success(request, f'Role {role.name} updated.')
        return redirect('erp:role_list')
    perms = {p.section: p for p in role.permissions.all()}
    return render(request, 'portal/role_form.html', {
        'role': role, 'perms': perms, 'sections': RolePermission.SECTIONS, 'edit': True,
    })


@erp_section_required('rfq')
def erp_rfq_list(request):
    rfqs = RFQ.objects.all().select_related('category', 'created_by')
    status = request.GET.get('status')
    if status:
        rfqs = rfqs.filter(status=status)
    return render(request, 'portal/rfq_list.html', {'rfqs': rfqs})


@erp_login_required
def erp_rfq_create(request):
    categories = RFQCategory.objects.filter(is_active=True)
    events = Event.objects.all()
    if request.method == 'POST':
        from decimal import Decimal
        closing_date_str = request.POST.get('closing_date', '')
        closing_date = timezone.datetime.strptime(closing_date_str, '%Y-%m-%dT%H:%M') if closing_date_str else timezone.now()
        budget = request.POST.get('estimated_budget', '').strip()
        try:
            rfq = RFQ.objects.create(
                event_id=request.POST.get('event_id') or None,
                category_id=request.POST.get('category_id') or None,
                title=request.POST.get('title', ''),
                description=request.POST.get('description', ''),
                deliverables=request.POST.get('deliverables', ''),
                terms_and_conditions=request.POST.get('terms_and_conditions', ''),
                priority=request.POST.get('priority', 'normal'),
                status='draft',
                closing_date=closing_date,
                estimated_budget=Decimal(budget) if budget else None,
                contact_person=request.POST.get('contact_person', ''),
                contact_email=request.POST.get('contact_email', ''),
                contact_phone=request.POST.get('contact_phone', ''),
                site_visit_required=request.POST.get('site_visit_required') == 'on',
                documents=request.FILES.get('documents'),
                created_by=request.user,
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f'RFQ create error: {e}')
            messages.error(request, f'Error creating RFQ: {e}. Please try again without a document or contact support.')
            return render(request, 'portal/rfq_form.html', {
                'categories': categories, 'events': events, 'edit': False,
            })
        messages.success(request, f'RFQ {rfq.rfq_number} created. Review and publish when ready.')
        return redirect('erp:rfq_detail', pk=rfq.pk)
    return render(request, 'portal/rfq_form.html', {
        'categories': categories, 'events': events, 'edit': False,
    })


@erp_section_required('rfq')
def erp_rfq_detail(request, pk):
    rfq = get_object_or_404(RFQ.objects.select_related('category', 'created_by', 'event'), pk=pk)
    quotations = rfq.quotations.all().select_related('provider').prefetch_related('documents')
    return render(request, 'portal/rfq_detail.html', {
        'rfq': rfq, 'quotations': quotations, 'now': timezone.now(),
    })


@erp_login_required
def erp_rfq_edit(request, pk):
    rfq = get_object_or_404(RFQ, pk=pk)
    categories = RFQCategory.objects.filter(is_active=True)
    events = Event.objects.all()
    if request.method == 'POST':
        from decimal import Decimal
        rfq.event_id = request.POST.get('event_id') or None
        rfq.category_id = request.POST.get('category_id') or None
        rfq.title = request.POST.get('title', '')
        rfq.description = request.POST.get('description', '')
        rfq.deliverables = request.POST.get('deliverables', '')
        rfq.terms_and_conditions = request.POST.get('terms_and_conditions', '')
        rfq.priority = request.POST.get('priority', 'normal')
        closing_date_str = request.POST.get('closing_date', '')
        if closing_date_str:
            rfq.closing_date = timezone.datetime.strptime(closing_date_str, '%Y-%m-%dT%H:%M')
        budget = request.POST.get('estimated_budget', '').strip()
        rfq.estimated_budget = Decimal(budget) if budget else None
        rfq.contact_person = request.POST.get('contact_person', '')
        rfq.contact_email = request.POST.get('contact_email', '')
        rfq.contact_phone = request.POST.get('contact_phone', '')
        rfq.site_visit_required = request.POST.get('site_visit_required') == 'on'
        if request.FILES.get('documents'):
            rfq.documents = request.FILES['documents']
        try:
            rfq.save()
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f'RFQ edit error: {e}')
            messages.error(request, f'Error saving RFQ: {e}. Please try again without a new document or contact support.')
            return render(request, 'portal/rfq_form.html', {
                'rfq': rfq, 'categories': categories, 'events': events, 'edit': True,
            })
        messages.success(request, 'RFQ updated.')
        return redirect('erp:rfq_detail', pk=rfq.pk)
    return render(request, 'portal/rfq_form.html', {
        'rfq': rfq, 'categories': categories, 'events': events, 'edit': True,
    })


@erp_login_required
def erp_rfq_publish(request, pk):
    rfq = get_object_or_404(RFQ, pk=pk)
    if rfq.status == 'draft':
        rfq.status = 'open'
        rfq.issue_date = timezone.now().date()
        rfq.published_at = timezone.now()
        rfq.save()
        from notifications.utils import send_rfq_published
        send_rfq_published(rfq)
        messages.success(request, f'RFQ {rfq.rfq_number} published. All providers have been notified.')
    return redirect('erp:rfq_detail', pk=rfq.pk)


@erp_login_required
def erp_rfq_close(request, pk):
    rfq = get_object_or_404(RFQ, pk=pk)
    if rfq.status == 'open':
        rfq.status = 'closed'
        rfq.save()
        messages.success(request, f'RFQ {rfq.rfq_number} closed. No further submissions accepted.')
    return redirect('erp:rfq_detail', pk=rfq.pk)


@erp_login_required
def erp_rfq_reopen(request, pk):
    rfq = get_object_or_404(RFQ, pk=pk)
    if rfq.status == 'closed' and rfq.closing_date and rfq.closing_date > timezone.now():
        rfq.status = 'open'
        rfq.save()
        messages.success(request, f'RFQ {rfq.rfq_number} re-opened. Providers can now submit proposals.')
    return redirect('erp:rfq_detail', pk=rfq.pk)


@erp_section_required('rfq')
def erp_quotation_detail(request, pk):
    quotation = get_object_or_404(
        Quotation.objects.select_related('rfq', 'provider').prefetch_related('documents'),
        pk=pk,
    )
    approvals = quotation.approvals.all().select_related('approved_by')
    return render(request, 'portal/quotation_detail.html', {
        'quotation': quotation, 'approvals': approvals,
    })


@erp_login_required
def erp_quotation_shortlist(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk)
    quotation.status = 'shortlisted'
    quotation.internal_notes = request.POST.get('internal_notes', '')
    quotation.save()
    name = quotation.provider.company_name if quotation.provider else quotation.submitter_company_name
    messages.success(request, f'{name} shortlisted.')
    return redirect('erp:rfq_detail', pk=quotation.rfq.pk)


@erp_login_required
def erp_quotation_reject(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk)
    quotation.status = 'rejected'
    quotation.save()
    from notifications.utils import send_quotation_rejected
    send_quotation_rejected(quotation)
    name = quotation.provider.company_name if quotation.provider else quotation.submitter_company_name
    messages.info(request, f'{name} has been notified of rejection.')
    return redirect('erp:rfq_detail', pk=quotation.rfq.pk)


@erp_login_required
def erp_quotation_approve_first(request, pk):
    """First director approves - marks as pending second approval."""
    quotation = get_object_or_404(Quotation, pk=pk)
    if quotation.status not in ('shortlisted', 'submitted'):
        messages.error(request, 'Quotation must be shortlisted first.')
        return redirect('erp:quotation_detail', pk=pk)
    existing = QuotationApproval.objects.filter(quotation=quotation, approval_order=1).exists()
    if existing:
        messages.warning(request, 'First approval already recorded.')
        return redirect('erp:quotation_detail', pk=pk)
    QuotationApproval.objects.create(
        quotation=quotation,
        approved_by=request.user,
        approval_order=1,
        comments=request.POST.get('comments', ''),
    )
    quotation.status = 'approved_by_first'
    quotation.save()
    # Notify remaining directors
    from notifications.utils import get_director_emails, send_html_email
    remaining = [e for e in get_director_emails() if e != request.user.email]
    if remaining:
        context = {
            'quotation': quotation,
            'rfq': quotation.rfq,
            'approved_by': request.user,
            'site_name': settings.SITE_NAME,
            'site_url': settings.SITE_URL,
        }
        send_html_email(
            f'First Approval Received - {quotation.quotation_number} - {quotation.provider.company_name}',
            'emails/quotation_first_approval.html', context, remaining,
        )
    messages.success(request, f'First approval recorded (1/2). Awaiting second director approval.')
    return redirect('erp:quotation_detail', pk=pk)


@erp_login_required
def erp_quotation_approve_second(request, pk):
    """Second director approves - quotation is accepted."""
    quotation = get_object_or_404(Quotation, pk=pk)
    if quotation.status != 'approved_by_first':
        messages.error(request, 'First approval required before second approval.')
        return redirect('erp:quotation_detail', pk=pk)
    existing = QuotationApproval.objects.filter(quotation=quotation, approval_order=2).exists()
    if existing:
        messages.warning(request, 'Second approval already recorded.')
        return redirect('erp:quotation_detail', pk=pk)
    QuotationApproval.objects.create(
        quotation=quotation,
        approved_by=request.user,
        approval_order=2,
        comments=request.POST.get('comments', ''),
    )
    quotation.status = 'acceptable'
    quotation.save()
    # Mark RFQ as awarded
    rfq = quotation.rfq
    rfq.status = 'awarded'
    rfq.save()

    # Auto-register anonymous submitter as a ServiceProvider, if not already one
    provider_password = None
    provider = quotation.provider
    if not provider:
        from django.contrib.auth.hashers import make_password
        from providers.models import ServiceProvider
        # Check if email already matches an existing provider
        existing_by_email = ServiceProvider.objects.filter(
            email__iexact=quotation.submitter_email
        ).first() if quotation.submitter_email else None
        if existing_by_email:
            provider = existing_by_email
            # Update company info from the quotation if different
            if quotation.submitter_company_name:
                provider.company_name = quotation.submitter_company_name
            if quotation.submitter_phone:
                provider.phone = quotation.submitter_phone
            if quotation.submitter_registration_number:
                provider.registration_number = quotation.submitter_registration_number
            if quotation.submitter_vat_number:
                provider.vat_number = quotation.submitter_vat_number
            provider.must_change_password = True
            provider.is_active = True
            provider.is_verified = True
            provider.save()
        else:
            # Default password = contact person name (lowercase, no spaces)
            contact_name = (quotation.submitter_contact_person or 'provider').strip().lower().replace(' ', '_')
            provider_password = contact_name
            provider = ServiceProvider.objects.create(
                email=quotation.submitter_email or f'{contact_name}@alansaar.org.za',
                password=make_password(provider_password),
                company_name=quotation.submitter_company_name or 'Unknown Company',
                company_type=quotation.submitter_company_type or 'other',
                registration_number=quotation.submitter_registration_number or '',
                vat_number=quotation.submitter_vat_number or '',
                phone=quotation.submitter_phone or '',
                contact_person=quotation.submitter_contact_person or '',
                is_verified=True,
                is_active=True,
                must_change_password=True,
            )
        quotation.provider = provider
        quotation.save()
    else:
        # Existing provider: force password change on next login
        provider.must_change_password = True
        provider.save()

    # Notify provider of acceptance (pending site meeting)
    from notifications.utils import send_quotation_accepted
    send_quotation_accepted(quotation, provider_password=provider_password)
    name = provider.company_name
    extra = f' Provider account created. Default password sent to {provider.email}.' if provider_password else ''
    messages.success(
        request,
        f'Quotation ACCEPTED PENDING APPROVAL (2/2). {name} has been notified.{extra} '
        f'A site meeting must be scheduled before final approval.'
    )
    return redirect('erp:quotation_detail', pk=pk)


@erp_login_required
def erp_quotation_schedule_meeting(request, pk):
    """Schedule a site meeting for an accepted-pending-approval quotation."""
    quotation = get_object_or_404(Quotation, pk=pk)
    if quotation.status != 'acceptable':
        messages.error(request, 'Quotation must be in "Accepted Pending Approval" status.')
        return redirect('erp:quotation_detail', pk=pk)
    if request.method == 'POST':
        meeting_date_str = request.POST.get('meeting_date', '').strip()
        if not meeting_date_str:
            messages.error(request, 'Please provide a meeting date and time.')
            return redirect('erp:quotation_detail', pk=pk)
        from django.utils.dateparse import parse_datetime
        meeting_date = parse_datetime(meeting_date_str)
        if not meeting_date:
            messages.error(request, 'Invalid date/time format.')
            return redirect('erp:quotation_detail', pk=pk)
        quotation.site_meeting_date = meeting_date
        quotation.save()
        from notifications.utils import send_quotation_site_meeting
        send_quotation_site_meeting(quotation, meeting_date)
        messages.success(request, f'Site meeting scheduled for {meeting_date.strftime("%d %b %Y at %H:%M")}. Provider notified.')
    return redirect('erp:quotation_detail', pk=pk)


@erp_login_required
def erp_quotation_approve_after_meeting(request, pk):
    """Final approval after site meeting — creates Expense + accounting entry."""
    quotation = get_object_or_404(Quotation, pk=pk)
    if quotation.status not in ('acceptable', 'accepted'):
        messages.error(request, 'Quotation must be in "Accepted Pending Approval" status.')
        return redirect('erp:quotation_detail', pk=pk)
    provider = quotation.provider
    if not provider:
        messages.error(request, 'No provider linked to this quotation.')
        return redirect('erp:quotation_detail', pk=pk)
    quotation.status = 'accepted'
    quotation.save()
    from providers.models import Expense
    existing_expense = Expense.objects.filter(provider=provider, description__contains=quotation.quotation_number).first()
    if not existing_expense:
        expense = Expense.objects.create(
            provider=provider,
            description=f'{quotation.rfq.rfq_number} - {quotation.rfq.title[:80]} - {quotation.quotation_number}',
            category='other',
            amount_excl=quotation.total_amount_excl,
            vat_amount=quotation.vat_amount,
            amount_incl=quotation.total_amount_incl,
            balance_due=quotation.total_amount_incl,
            expense_date=timezone.now().date(),
            due_date=timezone.now().date() + timezone.timedelta(days=30),
            notes=f'Final approval after site meeting. Quotation: {quotation.quotation_number}',
            created_by=request.user,
        )
    else:
        expense = existing_expense
    try:
        from accounting.auto_post import auto_post_accepted_quotation
        auto_post_accepted_quotation(quotation, expense, created_by=request.user)
    except Exception:
        pass
    try:
        from notifications.utils import send_quotation_fully_approved
        send_quotation_fully_approved(quotation)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception(f'Email failed for {quotation.quotation_number}: {e}')
    messages.success(
        request,
        f'Quotation FULLY APPROVED after site meeting. '
        f'Expense record created. Accounting entry posted. '
        f'{provider.company_name} now has a liability balance.'
    )
    return redirect('erp:quotation_detail', pk=pk)


@erp_login_required
def verify_registrations(request):
    from accounts.models import User as UserModel
    status_filter = request.GET.get('status', 'pending')
    users = UserModel.objects.filter(user_type='exhibitor').order_by('-date_joined')
    if status_filter == 'pending':
        users = users.filter(is_verified=False)
    elif status_filter == 'verified':
        users = users.filter(is_verified=True)
    return render(request, 'portal/verify_registrations.html', {
        'users': users,
        'status_filter': status_filter,
        'pending_count': UserModel.objects.filter(user_type='exhibitor', is_verified=False).count(),
    })


@erp_login_required
def verify_exhibitor(request, pk):
    from accounts.models import User as UserModel
    from django.utils import timezone
    user_obj = get_object_or_404(UserModel, pk=pk, user_type='exhibitor')
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'approve':
            user_obj.is_verified = True
            user_obj.verified_at = timezone.now()
            user_obj.save()
            from notifications.utils import send_account_activated
            try:
                send_account_activated(user_obj)
                messages.success(request, f'{user_obj.company_name or user_obj.username} has been verified and activated. Notification email sent.')
            except Exception as e:
                import logging
                logging.getLogger(__name__).exception(f'Approval email failed for {user_obj.email}: {e}')
                messages.warning(request, f'{user_obj.company_name or user_obj.username} has been verified, but the notification email could not be sent (error logged).')
        elif action == 'reject':
            user_obj.is_active = False
            user_obj.save()
            messages.warning(request, f'{user_obj.company_name or user_obj.username} registration has been rejected.')
    return redirect('erp:verify_registrations')


@erp_section_required('gate_takings')
def erp_gate_takings(request):
    from accounting.models import GateTaking
    from accounting.auto_post import auto_post_gate_taking

    if request.method == 'POST':
        date_str = request.POST.get('date', '').strip()
        cash_str = request.POST.get('cash_amount', '0').strip() or '0'
        card_str = request.POST.get('card_amount', '0').strip() or '0'
        notes = request.POST.get('notes', '').strip()
        cash_amount = Decimal(cash_str)
        card_amount = Decimal(card_str)
        if not date_str:
            messages.error(request, 'Please provide a date for the gate takings.')
            return redirect('erp:gate_takings')
        try:
            from datetime import date as date_cls
            gt_date = date_cls.fromisoformat(date_str)
        except ValueError:
            messages.error(request, 'Invalid date format.')
            return redirect('erp:gate_takings')
        if cash_amount < 0 or card_amount < 0:
            messages.error(request, 'Amounts cannot be negative.')
            return redirect('erp:gate_takings')
        if cash_amount == 0 and card_amount == 0:
            messages.error(request, 'Total amount must be greater than zero.')
            return redirect('erp:gate_takings')
        gate_taking = GateTaking.objects.create(
            date=gt_date,
            cash_amount=cash_amount,
            card_amount=card_amount,
            notes=notes,
            recorded_by=request.user,
        )
        try:
            auto_post_gate_taking(gate_taking, created_by=request.user)
            if gate_taking.journal_entry:
                messages.success(request, f'Gate takings for {gt_date} recorded and posted (JE {gate_taking.journal_entry.entry_number}).')
            else:
                messages.warning(request, 'Gate takings saved, but accounting accounts are missing so no journal entry was posted.')
        except Exception:
            import logging
            logging.getLogger(__name__).exception(f'auto_post_gate_taking failed for GateTaking {gate_taking.pk}')
            messages.warning(request, 'Gate takings saved, but the journal entry could not be posted (error logged).')
        return redirect('erp:gate_takings')

    entries = GateTaking.objects.select_related('recorded_by', 'journal_entry').all()
    total_cash = entries.aggregate(t=Sum('cash_amount'))['t'] or Decimal('0')
    total_card = entries.aggregate(t=Sum('card_amount'))['t'] or Decimal('0')
    total_all = total_cash + total_card
    return render(request, 'portal/gate_takings.html', {
        'entries': entries,
        'total_cash': total_cash,
        'total_card': total_card,
        'total_all': total_all,
    })


@erp_section_required('gate_takings')
def gate_takings_report(request):
    from accounting.models import GateTaking

    date_from = request.GET.get('from', '').strip()
    date_to = request.GET.get('to', '').strip()
    entries = GateTaking.objects.select_related('recorded_by').all()
    if date_from:
        entries = entries.filter(date__gte=date_from)
    if date_to:
        entries = entries.filter(date__lte=date_to)
    entries = entries.order_by('date', 'created_at')
    total_cash = entries.aggregate(t=Sum('cash_amount'))['t'] or Decimal('0')
    total_card = entries.aggregate(t=Sum('card_amount'))['t'] or Decimal('0')
    total_all = total_cash + total_card

    daily = []
    for entry in entries:
        row = next((d for d in daily if d['date'] == entry.date), None)
        if row is None:
            row = {'date': entry.date, 'cash': Decimal('0'), 'card': Decimal('0')}
            daily.append(row)
        row['cash'] += entry.cash_amount
        row['card'] += entry.card_amount
    for row in daily:
        row['total'] = row['cash'] + row['card']

    return render(request, 'portal/gate_takings_report.html', {
        'entries': entries,
        'daily': daily,
        'total_cash': total_cash,
        'total_card': total_card,
        'total_all': total_all,
        'date_from': date_from,
        'date_to': date_to,
    })


@erp_section_required('debt_declarations')
def erp_debt_declarations(request):
    from invoices.debt import get_exhibitor_outstanding, maybe_default_declaration
    from notifications.utils import send_debt_declaration_approval_request

    if request.method == 'POST':
        exhibitor_id = request.POST.get('exhibitor_id', '').strip()
        total_debt_str = request.POST.get('total_debt', '').strip()
        reason = request.POST.get('reason', '').strip()
        exhibitor = get_object_or_404(User, pk=exhibitor_id, user_type='exhibitor')
        try:
            total_debt = Decimal(total_debt_str)
        except (ValueError, TypeError):
            total_debt = Decimal('0')

        schedules = []
        for i in range(3):
            due = request.POST.get(f'date_{i}', '').strip()
            amt = request.POST.get(f'amount_{i}', '').strip()
            if not due:
                continue
            try:
                d = timezone.datetime.strptime(due, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                messages.error(request, f'Invalid date on schedule line {i + 1}.')
                return redirect('erp:debt_declarations')
            try:
                a = Decimal(amt)
            except (ValueError, TypeError):
                a = Decimal('0')
            schedules.append((d, a))

        if total_debt <= 0:
            messages.error(request, 'Total acknowledged debt must be greater than zero.')
            return redirect('erp:debt_declarations')
        if not schedules:
            messages.error(request, 'Add at least one agreed payment date.')
            return redirect('erp:debt_declarations')
        if any(a <= 0 for _, a in schedules):
            messages.error(request, 'Each scheduled payment amount must be greater than zero.')
            return redirect('erp:debt_declarations')

        outstanding = get_exhibitor_outstanding(exhibitor)
        count = DebtDeclaration.objects.count() + 1
        declaration_number = f"ACD-{timezone.now().strftime('%Y%m%d')}-{count:03d}"
        while DebtDeclaration.objects.filter(declaration_number=declaration_number).exists():
            count += 1
            declaration_number = f"ACD-{timezone.now().strftime('%Y%m%d')}-{count:03d}"

        declaration = DebtDeclaration.objects.create(
            declaration_number=declaration_number,
            exhibitor=exhibitor,
            total_debt=total_debt,
            outstanding_at_creation=outstanding,
            reason=reason,
            status='pending',
            initiated_by=request.user,
        )
        for due, amt in schedules:
            DebtPaymentSchedule.objects.create(
                declaration=declaration, due_date=due, amount=amt, status='pending',
            )
        try:
            send_debt_declaration_approval_request(declaration)
        except Exception:
            import logging
            logging.getLogger(__name__).exception(f'Approval request email failed for {declaration_number}')
        messages.success(
            request,
            f'Declaration {declaration_number} created and sent to all directors for authorisation '
            f'(2 approvals required). Outstanding debt: R{outstanding}.'
        )
        return redirect('erp:debt_declaration_detail', pk=declaration.pk)

    status_filter = request.GET.get('status', '')
    declarations = DebtDeclaration.objects.select_related('exhibitor', 'initiated_by').prefetch_related('payment_schedules')
    if status_filter:
        declarations = declarations.filter(status=status_filter)

    for decl in declarations:
        try:
            maybe_default_declaration(decl)
        except Exception:
            import logging
            logging.getLogger(__name__).exception(f'default check failed for {decl.declaration_number}')

    exhibitors = User.objects.filter(user_type='exhibitor').order_by('company_name')
    return render(request, 'portal/debt_declarations.html', {
        'declarations': declarations,
        'status_filter': status_filter,
        'statuses': DebtDeclaration.STATUS_CHOICES,
        'exhibitors': exhibitors,
    })


@erp_section_required('debt_declarations')
def erp_debt_declaration_detail(request, pk):
    from invoices.debt import maybe_default_declaration, refresh_schedule_status
    declaration = get_object_or_404(
        DebtDeclaration.objects.select_related('exhibitor', 'initiated_by').prefetch_related('payment_schedules', 'approvals', 'approvals__user'),
        pk=pk,
    )
    refresh_schedule_status(declaration)
    maybe_default_declaration(declaration)
    declaration.refresh_from_db()

    approvals = {a.user_id: a for a in declaration.approvals.all()}
    directors = list(declaration.directors)
    director_rows = []
    for d in directors:
        row = {'user': d, 'approval': approvals.get(d.pk)}
        director_rows.append(row)
    schedules = list(DebtPaymentSchedule.objects.filter(declaration=declaration).order_by('due_date'))
    return render(request, 'portal/debt_declaration_detail.html', {
        'declaration': declaration,
        'director_rows': director_rows,
        'schedules': schedules,
        'user_acted': request.user.id in approvals,
        'is_director_viewer': _is_director(request.user),
    })


def _is_director(user):
    return user.is_authenticated and user.user_type in ('director', 'admin', 'superadmin')


@erp_section_required('debt_declarations')
def erp_debt_declaration_approve(request, pk):
    from notifications.utils import send_debt_declaration_approved, send_debt_declaration_approval_request
    declaration = get_object_or_404(DebtDeclaration, pk=pk)
    if not _is_director(request.user):
        messages.error(request, 'Only directors may authorise debt declarations.')
        return redirect('erp:debt_declaration_detail', pk=pk)

    existing = DebtDeclarationApproval.objects.filter(declaration=declaration, user=request.user).first()
    if existing:
        if existing.action == 'approve':
            messages.info(request, 'You have already authorised this declaration.')
        else:
            messages.warning(request, 'You previously rejected this declaration.')
    else:
        DebtDeclarationApproval.objects.create(
            declaration=declaration, user=request.user, action='approve',
        )
        messages.success(request, f'{request.user.get_full_name() or request.user.username} has authorised the declaration.')

    if declaration.status == 'pending' and declaration.approval_count >= 2:
        declaration.status = 'active'
        declaration.approved_at = timezone.now()
        declaration.save(update_fields=['status', 'approved_at'])
        try:
            send_debt_declaration_approved(declaration)
            messages.success(request, f'Payment plan {declaration.declaration_number} AUTHORISED (2 directors). Exhibitor notified.')
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Approved email failed')

    try:
        send_debt_declaration_approval_request(declaration)
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Director update email failed')
    return redirect('erp:debt_declaration_detail', pk=pk)


@erp_section_required('debt_declarations')
def erp_debt_declaration_reject(request, pk):
    from notifications.utils import send_debt_declaration_approval_request
    declaration = get_object_or_404(DebtDeclaration, pk=pk)
    if not _is_director(request.user):
        messages.error(request, 'Only directors may reject debt declarations.')
        return redirect('erp:debt_declaration_detail', pk=pk)

    existing = DebtDeclarationApproval.objects.filter(declaration=declaration, user=request.user).first()
    if existing:
        messages.info(request, 'Your decision on this declaration is already recorded.')
    else:
        DebtDeclarationApproval.objects.create(
            declaration=declaration, user=request.user, action='reject',
        )
        messages.success(request, f'{request.user.get_full_name() or request.user.username} has rejected the declaration.')

    try:
        send_debt_declaration_approval_request(declaration)
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Director update email failed')
    return redirect('erp:debt_declaration_detail', pk=pk)


@erp_section_required('debt_declarations')
def erp_debt_declaration_schedule(request, pk, schedule_id):
    from invoices.debt import apply_declaration_payment, maybe_default_declaration
    declaration = get_object_or_404(DebtDeclaration, pk=pk)
    schedule = get_object_or_404(DebtPaymentSchedule, pk=schedule_id, declaration=declaration)
    if request.method != 'POST':
        return redirect('erp:debt_declaration_detail', pk=pk)

    action = request.POST.get('action', '')
    remark = request.POST.get('remark', '').strip()

    if action == 'paid':
        payment_method = request.POST.get('payment_method', 'cash')
        if payment_method not in ('cash', 'eft'):
            payment_method = 'cash'
        if schedule.status == 'paid':
            messages.info(request, 'This scheduled date is already marked as paid.')
        else:
            payments = apply_declaration_payment(schedule, payment_method, remark, request.user)
            if not payments:
                messages.error(
                    request,
                    'No open invoice with an outstanding balance was found - payment was NOT applied.'
                )
            else:
                total = sum(p.amount for p in payments)
                messages.success(
                    request,
                    f'Schedule {schedule.due_date} marked PAID. R{total} applied to '
                    f'invoice(s) and posted to accounting ({len(payments)} payment(s)).',
                )
    elif action == 'missed':
        if schedule.status == 'paid':
            messages.error(request, 'Cannot mark an already-paid date as missed.')
        else:
            schedule.status = 'missed'
            schedule.marked_by = request.user
            schedule.remark = remark or 'Missed agreed payment date'
            schedule.save(update_fields=['status', 'marked_by', 'remark'])
            defaulted = maybe_default_declaration(declaration)
            if defaulted:
                messages.warning(
                    request,
                    f'Schedule marked MISSED. All agreed dates have passed unpaid - declaration has DEFAULTED '
                    f'and directors, finance and the exhibitor have been notified.',
                )
            else:
                messages.warning(request, f'Schedule {schedule.due_date} marked MISSED.')
    else:
        messages.error(request, 'Unknown action.')

    return redirect('erp:debt_declaration_detail', pk=pk)


@erp_section_required('debt_declarations')
def erp_debt_declaration_letter(request, pk):
    from django.conf import settings as dj_settings
    declaration = get_object_or_404(
        DebtDeclaration.objects.select_related('exhibitor', 'initiated_by').prefetch_related('payment_schedules'),
        pk=pk,
    )
    return render(request, 'printouts/acknowledgement_of_debt.html', {
        'declaration': declaration,
        'schedules': declaration.payment_schedules.all(),
        'site_name': dj_settings.SITE_NAME,
        'site_url': dj_settings.SITE_URL,
    })
