from django.http import HttpResponse
from django.conf import settings
import os, re, logging

_svg_cache = {'content': None, 'mtime': 0}
logger = logging.getLogger('events.svg_view')


def serve_floor_plan(request):
    paths_to_try = ['floor_plans/dec_full_floor_plan.svg', 'dec_full_floor_plan.svg']
    raw = None
    for svg_rel_path in paths_to_try:
        if raw is not None:
            break
        try:
            from django.core.files.storage import default_storage
            if default_storage.exists(svg_rel_path):
                with default_storage.open(svg_rel_path, 'r') as f:
                    raw = f.read()
                if isinstance(raw, bytes):
                    raw = raw.decode('utf-8', errors='replace')
                logger.info(f'svg_view: loaded from storage path={svg_rel_path}')
        except Exception as e:
            logger.warning(f'svg_view: storage failed for {svg_rel_path}: {e}')
    for svg_rel_path in paths_to_try:
        if raw is not None:
            break
        try:
            import requests as http_requests
            r2_url = getattr(settings, 'AWS_S3_CUSTOM_DOMAIN', '')
            if r2_url:
                url = f"https://{r2_url}/{svg_rel_path}"
                resp = http_requests.get(url, timeout=30)
                if resp.status_code == 200:
                    raw = resp.text
                    logger.info(f'svg_view: loaded from public URL')
        except Exception:
            pass
    if raw is None:
        for svg_rel_path in paths_to_try:
            full_svg = os.path.join(str(settings.MEDIA_ROOT), svg_rel_path)
            if os.path.exists(full_svg):
                with open(full_svg, 'r', encoding='utf-8') as f:
                    raw = f.read()
                break
    if raw is None:
        logger.error('svg_view: all paths failed')
        return HttpResponse('Floor plan not found', status=404)
    if _svg_cache['content'] is None:
        raw = re.sub(r'width="[^"]*"', 'width="100%"', raw, count=1)
        raw = re.sub(r'height="[^"]*"', 'height="100%"', raw, count=1)
        raw = raw.replace('overflow="hidden"', 'overflow="visible"')
        svg_tag = re.search(r'<svg\b[^>]*>', raw)
        if svg_tag and 'overflow=' not in svg_tag.group():
            raw = raw[:svg_tag.end() - 1] + ' overflow="visible">' + raw[svg_tag.end():]
        _svg_cache['content'] = raw
    resp = HttpResponse(_svg_cache['content'], content_type='image/svg+xml')
    resp['Cache-Control'] = 'public, max-age=3600'
    return resp
