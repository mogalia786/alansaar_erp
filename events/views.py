from django.shortcuts import render, get_object_or_404
from .models import Event, Stall
import os, re, json
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


def floor_plan_view(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
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

    svg_content, fp_w, fp_h = _load_svg_content()

    return render(request, 'events/floor_plan_view.html', {
        'event': event,
        'svg_content': svg_content,
        'svg_w': fp_w,
        'svg_h': fp_h,
        'stalls_data': json.dumps(stalls_data),
    })
