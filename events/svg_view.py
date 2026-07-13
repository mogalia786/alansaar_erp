from django.http import HttpResponse
from django.conf import settings
import os, re

_svg_cache = {'content': None, 'mtime': 0}


def serve_floor_plan(request):
    full_svg = os.path.join(str(settings.MEDIA_ROOT), 'floor_plans', 'dec_full_floor_plan.svg')
    if not os.path.exists(full_svg):
        return HttpResponse('Floor plan not found', status=404)
    mtime = os.path.getmtime(full_svg)
    if _svg_cache['content'] is None or mtime != _svg_cache['mtime']:
        with open(full_svg, 'r', encoding='utf-8') as f:
            raw = f.read()
        raw = re.sub(r'width="[^"]*"', 'width="100%"', raw, count=1)
        raw = re.sub(r'height="[^"]*"', 'height="100%"', raw, count=1)
        raw = raw.replace('overflow="hidden"', 'overflow="visible"')
        svg_tag = re.search(r'<svg\b[^>]*>', raw)
        if svg_tag and 'overflow=' not in svg_tag.group():
            raw = raw[:svg_tag.end() - 1] + ' overflow="visible">' + raw[svg_tag.end():]
        _svg_cache['content'] = raw
        _svg_cache['mtime'] = mtime
    resp = HttpResponse(_svg_cache['content'], content_type='image/svg+xml')
    resp['Cache-Control'] = 'public, max-age=3600'
    return resp
