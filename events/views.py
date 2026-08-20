from django.shortcuts import render, get_object_or_404
from .models import Event, Stall, FloorPlanSection
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
import os, re, json
from decimal import Decimal
from django.conf import settings


_svg_cache = {'content': None, 'mtime': 0}


def home(request):
    events = Event.objects.filter(is_public=True, status__in=['published', 'ongoing'])[:6]
    return render(request, 'events/home.html', {'events': events})


def event_list(request):
    events = Event.objects.filter(is_public=True)
    return render(request, 'events/list.html', {'events': events})


def event_detail(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    zones = event.zones.filter(is_bookable=True)
    stalls = event.stalls.filter(status='available')
    return render(request, 'events/detail.html', {
        'event': event,
        'zones': zones,
        'available_stalls': stalls,
    })


def _get_svg_dims(path):
    fp_w, fp_h = 502485, 721189
    try:
        with open(path, 'r', encoding='utf-8') as f:
            head = f.read(2000)
        vb = re.search(r'viewBox="([^"]+)"', head)
        if vb:
            parts = vb.group(1).split()
            fp_w = int(float(parts[2]))
            fp_h = int(float(parts[3]))
    except Exception:
        pass
    return fp_w, fp_h


def _load_svg_content():
    global _svg_cache
    if _svg_cache['content'] is not None:
        return _svg_cache['content'], _svg_cache['fp_w'], _svg_cache['fp_h']
    paths_to_try = ['floor_plans/dec_full_floor_plan.svg', 'dec_full_floor_plan.svg']
    raw = None
    for svg_rel_path in paths_to_try:
        if raw is not None:
            break
        try:
            from django.core.files.storage import default_storage
            print(f'SVG loader: trying storage path={svg_rel_path}, storage={type(default_storage).__name__}')
            if default_storage.exists(svg_rel_path):
                f = default_storage.open(svg_rel_path)
                raw = f.read()
                f.close()
                if isinstance(raw, bytes):
                    raw = raw.decode('utf-8', errors='replace')
                print(f'SVG loader: loaded from storage path={svg_rel_path}, size={len(raw)}')
        except Exception as e:
            print(f'SVG loader: storage failed for {svg_rel_path}: {e}')
    for svg_rel_path in paths_to_try:
        if raw is not None:
            break
        try:
            import requests as http_requests
            r2_url = settings.AWS_S3_CUSTOM_DOMAIN
            if r2_url:
                url = f"https://{r2_url}/{svg_rel_path}"
                print(f'SVG loader: trying public URL={url}')
                resp = http_requests.get(url, timeout=30)
                if resp.status_code == 200:
                    raw = resp.text
                    print(f'SVG loader: loaded from public URL, size={len(raw)}')
                else:
                    print(f'SVG loader: public URL returned {resp.status_code}')
        except Exception as e:
            print(f'SVG loader: public URL failed for {svg_rel_path}: {e}')
    if raw is None:
        for svg_rel_path in paths_to_try:
            full_svg = os.path.join(str(settings.MEDIA_ROOT), svg_rel_path)
            if os.path.exists(full_svg):
                with open(full_svg, 'r', encoding='utf-8') as f:
                    raw = f.read()
                print(f'SVG loader: loaded from local file={full_svg}, size={len(raw)}')
                break
    if raw is None:
        print('SVG loader: all paths failed, returning empty')
        return '', 502485, 721189
    vb = re.search(r'viewBox="([^"]+)"', raw)
    fp_w, fp_h = 502485, 721189
    if vb:
        parts = vb.group(1).split()
        fp_w = int(float(parts[2]))
        fp_h = int(float(parts[3]))
    raw = raw.replace('overflow="hidden"', 'overflow="visible"')
    svg_tag = re.search(r'<svg\b[^>]*>', raw)
    if svg_tag and 'overflow=' not in svg_tag.group():
        raw = raw[:svg_tag.end() - 1] + ' overflow="visible">' + raw[svg_tag.end():]
    raw = re.sub(r'width="[^"]*"', f'width="{fp_w}"', raw, count=1)
    raw = re.sub(r'height="[^"]*"', f'height="{fp_h}"', raw, count=1)
    _svg_cache = {'content': raw, 'mtime': 0, 'fp_w': fp_w, 'fp_h': fp_h}
    return raw, fp_w, fp_h


def floor_plan_view(request, event_id, section_id=None):
    event = get_object_or_404(Event, pk=event_id)
    sections = event.floor_plan_sections.all().order_by('display_order')
    active_section_id = section_id or request.GET.get('section')
    
    if not sections.exists():
        svg_content, fp_w, fp_h = _load_svg_content()
        stalls = event.stalls.all().select_related('zone').order_by('name')
        stalls_data = [{
            'id': s.id, 'name': s.name,
            'x': s.position_x, 'y': s.position_y,
            'w': s.width, 'h': s.height,
            'price': float(s.total_price),
            'status': s.status,
            'size_sqm': float(s.size_sqm),
            'zone': s.zone.name if s.zone else '',
        } for s in stalls]
        return render(request, 'events/floor_plan_view.html', {
            'event': event,
            'svg_content': svg_content,
            'svg_w': fp_w,
            'svg_h': fp_h,
            'stalls_data': json.dumps(stalls_data),
            'sections': [],
            'active_section': None,
        })

    if active_section_id:
        active_section = FloorPlanSection.objects.filter(pk=active_section_id, event=event).first()
    if not active_section_id or not active_section:
        active_section = sections.first()

    stalls = event.stalls.filter(section=active_section).select_related('zone').order_by('name')
    scale = float(active_section.scale_factor)
    stalls_data = [{
        'id': s.id, 'name': s.name,
        'x': round(s.position_x * scale / 1000),
        'y': round(s.position_y * scale / 1000),
        'w': round(s.width * scale / 1000),
        'h': round(s.height * scale / 1000),
        'price': float(s.total_price),
        'status': s.status,
        'size_sqm': float(s.size_sqm),
        'zone': s.zone.name if s.zone else '',
        'rotation': s.rotation,
    } for s in stalls]

    sections_data = [{
        'id': s.id,
        'name': s.name,
        'image_url': s.section_image.url if s.section_image else '',
        'width': s.original_width,
        'height': s.original_height,
        'stall_count': s.stalls.count(),
        'scale_factor': s.scale_factor,
    } for s in sections]

    return render(request, 'events/floor_plan_view.html', {
        'event': event,
        'sections': sections_data,
        'active_section': {
            'id': active_section.id,
            'name': active_section.name,
            'image_url': active_section.section_image.url if active_section.section_image else '',
            'width': active_section.original_width,
            'height': active_section.original_height,
            'scale_factor': active_section.scale_factor,
        },
        'stalls_data': json.dumps(stalls_data),
        'svg_content': '',
        'svg_w': active_section.original_width if active_section else 1600,
        'svg_h': active_section.original_height if active_section else 900,
    })


@require_POST
def stall_update(request, event_id, stall_id):
    event = get_object_or_404(Event, pk=event_id)
    stall = get_object_or_404(Stall, pk=stall_id, event=event)
    data = json.loads(request.body)
    scale = 1000 / float(stall.section.scale_factor) if stall.section else 1
    if 'position_x' in data:
        stall.position_x = round(data['position_x'] * scale)
    if 'position_y' in data:
        stall.position_y = round(data['position_y'] * scale)
    if 'width' in data:
        stall.width = round(float(data['width']) * 1000)
    if 'height' in data:
        stall.height = round(float(data['height']) * 1000)
        stall.size_sqm = round(float(data['width'] if 'width' in data else stall.width / 1000) * float(data['height']), 2)
    if 'rotation' in data:
        stall.rotation = int(data['rotation'])
    if 'name' in data:
        new_name = data['name'].strip()
        if new_name and new_name != stall.name:
            if Stall.objects.filter(section=stall.section, name=new_name).exclude(pk=stall.pk).exists():
                return JsonResponse({'ok': False, 'error': f'Stall "{new_name}" already exists in this section'})
            stall.name = new_name
    if data.get('delete'):
        stall.delete()
        return JsonResponse({'ok': True, 'deleted': True})
    if 'base_price' in data:
        stall.base_price = Decimal(str(data['base_price']))
    stall.save()
    section = stall.section
    scale_fwd = float(section.scale_factor) if section else 1
    return JsonResponse({
        'ok': True,
        'id': stall.id,
        'name': stall.name,
        'x': round(stall.position_x * scale_fwd / 1000),
        'y': round(stall.position_y * scale_fwd / 1000),
        'w': round(stall.width * scale_fwd / 1000),
        'h': round(stall.height * scale_fwd / 1000),
        'rotation': stall.rotation,
        'size_sqm': float(stall.size_sqm),
        'base_price': float(stall.base_price),
    })


@require_POST
def stall_create(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    data = json.loads(request.body)
    section_id = data.get('section_id')
    section = get_object_or_404(FloorPlanSection, pk=section_id, event=event) if section_id else None
    name = data.get('name', '').strip()
    if not name:
        return JsonResponse({'ok': False, 'error': 'Name is required'})
    if section and Stall.objects.filter(section=section, name=name).exists():
        return JsonResponse({'ok': False, 'error': f'Stall "{name}" already exists in this section'})
    scale = 1000 / float(section.scale_factor) if section else 1
    width_m = float(data.get('width', 3))
    height_m = float(data.get('height', 3))
    price = Decimal(str(data.get('price', 0)))
    stall = Stall.objects.create(
        event=event,
        section=section,
        name=name,
        position_x=round(float(data.get('x', 0)) * scale),
        position_y=round(float(data.get('y', 0)) * scale),
        width=round(width_m * 1000),
        height=round(height_m * 1000),
        size_sqm=round(width_m * height_m, 2),
        base_price=price,
        status='available',
    )
    scale_fwd = float(section.scale_factor) if section else 1
    return JsonResponse({
        'ok': True,
        'id': stall.id,
        'name': stall.name,
        'x': round(stall.position_x * scale_fwd / 1000),
        'y': round(stall.position_y * scale_fwd / 1000),
        'w': round(stall.width * scale_fwd / 1000),
        'h': round(stall.height * scale_fwd / 1000),
        'price': float(stall.base_price),
        'size_sqm': float(stall.size_sqm),
        'status': stall.status,
        'rotation': 0,
    })


@csrf_exempt
def remote_reset(request, event_id, token):
    if token != 'dss2026reset':
        return HttpResponse('Invalid token', status=403)
    if request.GET.get('confirm') != 'yes':
        return HttpResponse('Add ?confirm=yes to run')
    from bookings.models import Booking
    from invoices.models import Invoice, Payment
    event = get_object_or_404(Event, pk=event_id)
    payments = Payment.objects.filter(invoice__booking__event=event)
    invoices = Invoice.objects.filter(booking__event=event)
    bookings = Booking.objects.filter(event=event)
    stalls = Stall.objects.filter(event=event)
    p_count = payments.count()
    i_count = invoices.count()
    b_count = bookings.count()
    s_count = stalls.count()
    payments.delete()
    invoices.delete()
    bookings.delete()
    stalls.delete()
    stall_file = os.path.join(str(settings.BASE_DIR), 'stall_export.json')
    created = 0
    skipped_sections = []
    if os.path.exists(stall_file):
        with open(stall_file, 'r') as f:
            data = json.load(f)
        sections_map = {}
        for s in FloorPlanSection.objects.filter(event=event):
            sections_map[s.name] = s
        section_defs = {
            'Main Hall': {'display_order': 1, 'original_width': 4959, 'original_height': 7009, 'scale_factor': 35.0, 'section_image': 'floor_plan_sections/1_main_hall_Oz2k97q.png'},
            'East Lawn': {'display_order': 2, 'original_width': 9917, 'original_height': 7017, 'scale_factor': 87.5, 'section_image': 'floor_plan_sections/1_east_lawn_EfYF7ud.png'},
            'North Plaza': {'display_order': 3, 'original_width': 4959, 'original_height': 7009, 'scale_factor': 35.0, 'section_image': 'floor_plan_sections/1_north_plaza_N3e1J9d.png'},
        }
        for name, defs in section_defs.items():
            if name not in sections_map:
                sec = FloorPlanSection.objects.create(event=event, name=name, **defs)
                sections_map[name] = sec
        for d in data:
            section = sections_map.get(d['section'])
            if not section:
                skipped_sections.append(d['section'])
                continue
            Stall.objects.create(
                event=event, section=section, name=d['name'],
                position_x=d['position_x'], position_y=d['position_y'],
                width=d['width'], height=d['height'], size_sqm=d['size_sqm'],
                base_price=Decimal(str(d['base_price'])),
                status=d.get('status', 'available'),
                rotation=d.get('rotation', 0),
                has_water=d.get('has_water', False),
                is_corner=d.get('is_corner', False),
                is_near_entrance=d.get('is_near_entrance', False),
                is_accessible=d.get('is_accessible', False),
            )
            created += 1
    sections_info = ', '.join(f'{s.name}: {s.stalls.count()}' for s in FloorPlanSection.objects.filter(event=event))
    return HttpResponse(
        f'Reset complete for {event.name}:<br>'
        f'Deleted: {b_count} bookings, {i_count} invoices, {p_count} payments, {s_count} stalls<br>'
        f'Imported: {created} stalls<br>'
        f'Sections: {sections_info}'
    )
