"""
setup_floor_plan_sections — v3
OCR-based stall naming with vector-based boundary detection.
No prefixes — uses actual PDF labels where found.
"""
import os
import fitz
import numpy as np
import re
from decimal import Decimal
from collections import Counter
from django.core.management.base import BaseCommand
from django.core.files import File
from django.conf import settings
from events.models import Event, FloorPlanSection, Stall

RENDER_DPI = 600

PDF_MAP = [
    ('Durban Summer Souk 2026 Floor plan Presentation 1.3.pdf', 'Main Hall', 1),
    ('Durban Summer Souk 2026 EastLawn Floor plan Presentation.pdf', 'East Lawn', 2),
    ('Durban Summer Souk 2026 North Plaza Floor plan Presentation 1.0.pdf', 'North Plaza', 3),
]

GRID_PARAMS = {
    'Main Hall': {'grid_pts': 4.2, 'grid_px': 35, 'h_count': 134, 'v_count': 131},
    'East Lawn': {'grid_pts': 10.5, 'grid_px': 88, 'h_count': 74, 'v_count': 90},
    'North Plaza': {'grid_pts': 4.2, 'grid_px': 35, 'h_count': 169, 'v_count': 122},
}


def get_price(w, h):
    prices = {
        (3, 3): Decimal('5000'), (3, 2): Decimal('3500'), (2, 3): Decimal('3500'),
        (3, 4): Decimal('6500'), (4, 3): Decimal('6500'), (3, 5): Decimal('7500'),
        (5, 3): Decimal('7500'), (5, 4): Decimal('9000'), (4, 5): Decimal('9000'),
        (6, 6): Decimal('15000'), (8, 3): Decimal('12000'), (3, 8): Decimal('12000'),
        (3, 6): Decimal('9000'), (6, 3): Decimal('9000'), (1, 1): Decimal('1000'),
    }
    return prices.get((w, h), prices.get((h, w), Decimal(str(max(w, h) * 500))))


def detect_grid_from_pdf(page, expected_spacing=None):
    drawings = page.get_drawings()
    grid_lines = [d for d in drawings if d.get('color') and abs(d['color'][0] - 0.73) < 0.10 and d.get('fill') is None]

    h_segs, v_segs = [], []
    for d in grid_lines:
        for item in d.get('items', []):
            if item[0] == 'l':
                p1, p2 = item[1], item[2]
                if abs(p1.y - p2.y) < 2:
                    h_segs.append(round((p1.y + p2.y) / 2, 1))
                elif abs(p1.x - p2.x) < 2:
                    v_segs.append(round((p1.x + p2.x) / 2, 1))

    def cluster(positions, threshold=1.5):
        positions = sorted(set(positions))
        if not positions:
            return []
        clusters, current = [], [positions[0]]
        for p in positions[1:]:
            if p - current[-1] <= threshold:
                current.append(p)
            else:
                clusters.append(round(np.mean(current), 2))
                current = [p]
        clusters.append(round(np.mean(current), 2))
        return clusters

    h_raw, v_raw = cluster(h_segs), cluster(v_segs)
    h_spacings = [h_raw[i + 1] - h_raw[i] for i in range(len(h_raw) - 1)] if len(h_raw) > 1 else []
    h_typical = [s for s in h_spacings if 2 < s < 20]
    if not h_typical:
        return None

    if expected_spacing:
        dominant_spacing = expected_spacing
    else:
        dominant_spacing = round(np.median(h_typical), 2)

    def generate_grid(raw_positions, spacing):
        if not raw_positions:
            return []
        origin = raw_positions[0]
        last = raw_positions[-1]
        count = round((last - origin) / spacing) + 1
        return [round(origin + i * spacing, 2) for i in range(count)]

    h_positions = generate_grid(h_raw, dominant_spacing)
    v_positions = generate_grid(v_raw, dominant_spacing)

    grid_px = dominant_spacing * RENDER_DPI / 72
    if len(h_positions) < 2 or len(v_positions) < 2:
        return None

    floor_w_m = round((v_positions[-1] - v_positions[0]) / dominant_spacing)
    floor_h_m = round((h_positions[-1] - h_positions[0]) / dominant_spacing)

    return {
        'h_positions': h_positions, 'v_positions': v_positions,
        'grid_pts': dominant_spacing, 'grid_px': grid_px,
        'origin_x_px': v_positions[0] * RENDER_DPI / 72,
        'origin_y_px': h_positions[0] * RENDER_DPI / 72,
        'floor_w_m': floor_w_m, 'floor_h_m': floor_h_m,
    }


def detect_regions(page, grid_info):
    drawings = page.get_drawings()
    h_grid = grid_info['h_positions']
    v_grid = grid_info['v_positions']
    rows = grid_info['floor_h_m']
    cols = grid_info['floor_w_m']
    gpts = grid_info['grid_pts']
    tol = gpts * 0.6

    grey_fills = []
    for d in drawings:
        fill = d.get('fill')
        if not fill:
            continue
        if not (0.45 < fill[0] < 0.65 and 0.45 < fill[1] < 0.65 and 0.45 < fill[2] < 0.65):
            continue
        min_x = min_y = float('inf')
        max_x = max_y = float('-inf')
        for item in d.get('items', []):
            if item[0] == 're':
                r = item[1]
                for x, y in [(r.x0, r.y0), (r.x1, r.y1)]:
                    min_x, max_x = min(min_x, x), max(max_x, x)
                    min_y, max_y = min(min_y, y), max(max_y, y)
            elif item[0] == 'l':
                for p in [item[1], item[2]]:
                    min_x, max_x = min(min_x, p.x), max(max_x, p.x)
                    min_y, max_y = min(min_y, p.y), max(max_y, p.y)
        if min_x < float('inf'):
            grey_fills.append((min_x, min_y, max_x, max_y))

    wall_drawings = []
    for d in drawings:
        if d.get('fill') is not None or not d.get('color'):
            continue
        r, g, b = d['color'][0], d['color'][1], d['color'][2]
        is_dark = r < 0.6 and g < 0.6 and b < 0.6
        is_saturated = max(r, g, b) > 0.5 and (max(r, g, b) - min(r, g, b)) > 0.2
        if is_dark or is_saturated:
            wall_drawings.append((d, True))

    h_walls = np.zeros((rows + 1, cols), dtype=bool)
    v_walls = np.zeros((cols + 1, rows), dtype=bool)

    def find_nearest(pos, positions, tolerance):
        best_i, best_dist = -1, float('inf')
        for i, gp in enumerate(positions):
            d = abs(pos - gp)
            if d <= tolerance and d < best_dist:
                best_dist = d
                best_i = i
        return best_i

    wall_segments = []
    for d, is_dark in wall_drawings:
        for item in d.get('items', []):
            if item[0] == 'l':
                p1, p2 = item[1], item[2]
                length = ((p2.x - p1.x) ** 2 + (p2.y - p1.y) ** 2) ** 0.5
                if length >= gpts * 0.8:
                    wall_segments.append((p1, p2, is_dark))
            elif item[0] == 're':
                r = item[1]
                corners = [fitz.Point(r.x0, r.y0), fitz.Point(r.x1, r.y0),
                           fitz.Point(r.x1, r.y1), fitz.Point(r.x0, r.y1)]
                for i in range(4):
                    p1, p2 = corners[i], corners[(i + 1) % 4]
                    length = ((p2.x - p1.x) ** 2 + (p2.y - p1.y) ** 2) ** 0.5
                    if length >= gpts * 0.8:
                        wall_segments.append((p1, p2, is_dark))

    for p1, p2, is_dark in wall_segments:
        seg_tol = gpts * 0.6
        is_h = abs(p1.y - p2.y) < 2
        is_v = abs(p1.x - p2.x) < 2
        if is_h:
            r = find_nearest((p1.y + p2.y) / 2, h_grid, seg_tol)
            if r is None or r < 0 or r > rows:
                continue
            xs, xe = min(p1.x, p2.x), max(p1.x, p2.x)
            c_start = c_end = -1
            for c in range(len(v_grid)):
                if v_grid[c] >= xs - seg_tol and c_start == -1:
                    c_start = c
                if v_grid[c] <= xe + seg_tol:
                    c_end = c
            if c_start >= 0 and c_end >= 0:
                for c in range(c_start, min(c_end, cols)):
                    sm = (v_grid[c] + (v_grid[c + 1] if c + 1 < len(v_grid) else v_grid[c] + gpts)) / 2
                    if xs <= sm + seg_tol and xe >= sm - seg_tol:
                        h_walls[r][c] = True
        elif is_v:
            c = find_nearest((p1.x + p2.x) / 2, v_grid, seg_tol)
            if c is None or c < 0 or c > cols:
                continue
            ys, ye = min(p1.y, p2.y), max(p1.y, p2.y)
            r_start = r_end = -1
            for r in range(len(h_grid)):
                if h_grid[r] >= ys - seg_tol and r_start == -1:
                    r_start = r
                if h_grid[r] <= ye + seg_tol:
                    r_end = r
            if r_start >= 0 and r_end >= 0:
                for r in range(r_start, min(r_end, rows)):
                    sm = (h_grid[r] + (h_grid[r + 1] if r + 1 < len(h_grid) else h_grid[r] + gpts)) / 2
                    if ys <= sm + seg_tol and ye >= sm - seg_tol:
                        v_walls[c][r] = True

    grid = np.zeros((rows, cols), dtype=np.int32)
    label = 0
    for r in range(rows):
        for c in range(cols):
            if grid[r, c] != 0:
                continue
            label += 1
            queue = [(r, c)]
            grid[r, c] = label
            while queue:
                cr, cc = queue.pop(0)
                for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nr, nc = cr + dr, cc + dc
                    if nr < 0 or nr >= rows or nc < 0 or nc >= cols:
                        continue
                    if grid[nr, nc] != 0:
                        continue
                    if dr == -1 and h_walls[cr][cc]:
                        continue
                    if dr == 1 and h_walls[cr + 1][cc]:
                        continue
                    if dc == -1 and v_walls[cc][cr]:
                        continue
                    if dc == 1 and v_walls[cc + 1][cr]:
                        continue
                    grid[nr, nc] = label
                    queue.append((nr, nc))

    regions = []
    for i in range(1, label + 1):
        cells = np.argwhere(grid == i)
        min_r, min_c = cells.min(axis=0)
        max_r, max_c = cells.max(axis=0)
        wm = int(max_c - min_c + 1)
        hm = int(max_r - min_r + 1)
        area = wm * hm
        fill = len(cells) / area if area > 0 else 0
        cx_pdf = (v_grid[min_c] + v_grid[min_c] + wm * gpts) / 2 if min_c < len(v_grid) else 0
        cy_pdf = (h_grid[min_r] + h_grid[min_r] + hm * gpts) / 2 if min_r < len(h_grid) else 0
        in_grey = False
        for gx0, gy0, gx1, gy1 in grey_fills:
            if gx0 < cx_pdf < gx1 and gy0 < cy_pdf < gy1:
                in_grey = True
                break
        regions.append({
            'min_r': int(min_r), 'min_c': int(min_c),
            'width_m': wm, 'height_m': hm, 'area_m2': area,
            'fill': round(fill, 2),
            'in_grey_fill': in_grey,
        })
    return regions


def run_ocr(image_path):
    import pytesseract
    from PIL import Image, ImageEnhance
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

    img = Image.open(image_path)
    gray = img.convert('L')
    enhanced = ImageEnhance.Contrast(gray).enhance(3.0)
    binary = enhanced.point(lambda p: 255 if p > 180 else 0)

    data = pytesseract.image_to_data(binary, config='--psm 11 --oem 3', output_type=pytesseract.Output.DICT)

    labels = []
    stall_re = re.compile(r'^(F?\d{1,3}|[A-Z][A-Za-z]+\s*\d*)$', re.IGNORECASE)
    skip_words = {'EXIT', 'ENTRANCE', 'BOOKSHOP', 'STORE', 'ROOM', 'FOOD', 'COURT',
                  'WASH', 'AREA', 'CAR', 'GEN', 'TOILET', 'ATM', 'GATE', 'SERVICE',
                  'DOORS', 'SPEED', 'FENCING', 'QUANTITIES', 'STREET', 'NAMES',
                  'VENUE', 'LAYOUT', 'HALL', 'COPYRIGHT', 'RESERVED', 'EXPO',
                  'SOLUTIONS', 'THROUGH', 'PARTNERSHIP', 'LED', 'EMMA', 'DOR',
                  'GENERATOR', 'JORDANIAN', 'PAVILION', 'DURBAN', 'SUMMER', 'SOUK',
                  'DEC', 'NORTH', 'PLAZA', 'EASTLAWN', 'MAIN', 'INFO', 'ENTERTAINMENT',
                  'MARQUEE', 'BOX', 'PO', 'CAPE', 'UNIT', 'COSMO', 'BUSINESS',
                  'PARK', 'KYLAMI', 'WESTMEAD', 'MIALNO', 'MCGREGOR', 'BEACONVALE',
                  'PAARDEN', 'EILAND', 'AYANDA', 'MZELEMU', 'AUGUST',
                  'STANDS', 'PARTNERSHIPS', 'CONDS', 'BAWAS', 'GINO'}
    skip_exact_2 = {'AD', 'AP', 'BG', 'BY', 'CD', 'CZ', 'DB', 'DH', 'EE', 'EO',
                    'ES', 'ET', 'FC', 'FE', 'FH', 'FN', 'FO', 'FP', 'GC', 'GJ',
                    'IE', 'IM', 'IP', 'LI', 'LJ', 'LX', 'NE', 'NG', 'OE', 'OF',
                    'OZ', 'PO', 'PS', 'QO', 'RA', 'SD', 'SJ', 'SS', 'SI', 'TA',
                    'TP', 'UL', 'UY', 'XB', 'XT', 'FD', 'NU', 'LM', 'LT', 'PN',
                    'SLO', 'SIS', 'SFS'}
    skip_exact_3 = {'ATE', 'OOM', 'OFO', 'OOF', 'ELE', 'POTE', 'FEEL', 'ICA',
                    'NIN', 'LIN', 'LIT', 'HET', 'PTT', 'OTH', 'AP', 'OFA'}
    for i in range(len(data['text'])):
        text = data['text'][i].strip()
        conf = int(data['conf'][i])
        if text and conf > 20:
            upper = text.upper().strip()
            if upper in skip_words or len(upper) <= 1:
                continue
            if upper in skip_exact_2 or upper in skip_exact_3:
                continue
            if len(upper) == 2 and not upper[0].isdigit() and not upper.startswith('F'):
                continue
            m = stall_re.match(text)
            if m:
                x, y, w, h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
                label_text = m.group(1).strip()
                labels.append({
                    'text': label_text,
                    'cx': x + w // 2, 'cy': y + h // 2,
                    'x': x, 'y': y, 'w': w, 'h': h,
                    'conf': conf,
                })
    return labels


def extract_pdf_text_labels(pdf_path):
    """Extract text labels directly from PDF text objects (vector text, not rasterized)."""
    doc = fitz.open(pdf_path)
    page = doc[0]
    blocks = page.get_text('dict')['blocks']
    labels = []
    stall_re = re.compile(r'^(NF\d{1,3}|F\d{1,3}|FO\d+|J\d{1,2}|\d{1,3})$', re.IGNORECASE)
    for b in blocks:
        if 'lines' not in b:
            continue
        for line in b['lines']:
            for span in line['spans']:
                text = span['text'].strip()
                if text and stall_re.match(text):
                    bbox = span['bbox']
                    cx = (bbox[0] + bbox[2]) / 2
                    cy = (bbox[1] + bbox[3]) / 2
                    labels.append({
                        'text': text,
                        'cx': cx * RENDER_DPI / 72,
                        'cy': cy * RENDER_DPI / 72,
                        'x': bbox[0] * RENDER_DPI / 72,
                        'y': bbox[1] * RENDER_DPI / 72,
                        'w': (bbox[2] - bbox[0]) * RENDER_DPI / 72,
                        'h': (bbox[3] - bbox[1]) * RENDER_DPI / 72,
                        'conf': 100,
                        'source': 'pdf',
                    })
    doc.close()
    return labels


NORTH_PLAZA_KNOWN_LABELS = [
    ('NF1', 88.3, 130.3), ('NF2', 85.3, 130.3), ('NF3', 82.2, 130.3),
    ('NF4', 79.2, 130.3), ('NF5', 75.8, 130.3), ('NF6', 72.8, 130.3),
    ('NF7', 69.9, 130.3), ('NF8', 67.0, 130.2),
    ('NF9', 64.0, 133.2), ('NF10', 63.8, 136.5),
    ('NF11', 63.9, 139.3), ('NF12', 63.7, 142.2),
    ('NF13', 65.0, 145.2), ('NF14', 68.0, 145.2), ('NF15', 71.0, 145.2),
    ('NF16', 75.8, 145.2), ('NF17', 79.0, 145.2), ('NF18', 82.0, 145.2),
    ('NF19', 85.0, 145.2), ('NF20', 88.1, 145.2),
    ('004', 35.8, 127.0), ('005', 38.9, 127.0),
    ('006', 41.9, 127.0), ('007', 44.9, 127.0), ('008', 47.9, 127.0),
    ('009', 50.9, 127.0), ('010', 54.0, 127.0), ('011', 57.0, 127.0),
    ('012', 57.0, 138.0), ('013', 54.0, 138.4),
    ('014', 51.0, 138.0), ('015', 48.0, 138.0), ('016', 45.0, 138.0),
    ('017', 41.9, 138.0), ('018', 38.9, 138.0), ('019', 35.9, 138.0),
    ('020', 32.8, 138.0),
    ('021', 32.8, 143.0), ('022', 35.8, 143.0), ('023', 38.9, 143.0),
    ('024', 41.9, 143.0), ('025', 44.9, 143.0), ('026', 47.9, 143.0),
    ('027', 50.9, 143.0), ('028', 53.9, 143.0), ('029', 56.9, 143.0),
]


def match_labels_to_regions(regions, labels, grid_info):
    gpts = grid_info['grid_pts']
    v_grid = grid_info['v_positions']
    h_grid = grid_info['h_positions']

    valid_label_re = re.compile(r'^(F\d{1,3}|FO\d+|NF\d+|J\d+|\d{1,3})$')
    labels = [l for l in labels if valid_label_re.match(l['text'])]

    for region in regions:
        min_r, min_c = region['min_r'], region['min_c']
        wm, hm = region['width_m'], region['height_m']

        center_x_pdf = v_grid[min_c] + (wm * gpts) / 2 if min_c < len(v_grid) else 0
        center_y_pdf = h_grid[min_r] + (hm * gpts) / 2 if min_r < len(h_grid) else 0
        center_x_px = center_x_pdf * RENDER_DPI / 72
        center_y_px = center_y_pdf * RENDER_DPI / 72

        best_label = None
        best_dist = float('inf')
        for label in labels:
            dx = label['cx'] - center_x_px
            dy = label['cy'] - center_y_px
            dist = (dx ** 2 + dy ** 2) ** 0.5
            region_diag_px = ((wm * gpts * RENDER_DPI / 72) ** 2 + (hm * gpts * RENDER_DPI / 72) ** 2) ** 0.5
            if dist < region_diag_px and dist < best_dist:
                best_dist = dist
                best_label = label

        if not region.get('label'):
            region['label'] = best_label['text'] if best_label else None

    used_labels = set()
    for region in regions:
        if region.get('label') and region['label'] in used_labels:
            region['label'] = None
        elif region.get('label'):
            used_labels.add(region['label'])

    return regions


class Command(BaseCommand):
    help = 'Setup floor plan sections with OCR-named stalls'

    def add_arguments(self, parser):
        parser.add_argument('--event', type=int, required=True)
        parser.add_argument('--pdf-dir', type=str, default=None)
        parser.add_argument('--clear', action='store_true')
        parser.add_argument('--min-area', type=int, default=2)
        parser.add_argument('--max-area', type=int, default=100)
        parser.add_argument('--min-fill', type=float, default=0.4)

    def handle(self, *args, **options):
        event = Event.objects.get(pk=options['event'])
        pdf_dir = options['pdf_dir'] or os.path.join(settings.MEDIA_ROOT, 'New Floor Plans')
        output_dir = os.path.join(settings.MEDIA_ROOT, 'floor_plan_sections')
        os.makedirs(output_dir, exist_ok=True)

        if options['clear']:
            self.stdout.write('Clearing existing data...')
            try:
                Stall.objects.filter(event=event).delete()
            except Exception:
                from django.db import connection
                with connection.cursor() as cursor:
                    cursor.execute('DELETE FROM events_stall WHERE event_id = %s', [event.id])
            FloorPlanSection.objects.filter(event=event).delete()

        total_stalls = 0

        for pdf_name, section_name, display_order in PDF_MAP:
            matching_pdf = None
            for f in os.listdir(pdf_dir):
                if pdf_name.lower() in f.lower() and f.lower().endswith('.pdf'):
                    matching_pdf = f
                    break
            if not matching_pdf:
                self.stdout.write(self.style.WARNING(f'PDF not found for {section_name}'))
                continue

            pdf_path = os.path.join(pdf_dir, matching_pdf)
            section_key = section_name.lower().replace(' ', '_')
            png_filename = f'{event.id}_{section_key}.png'
            png_path = os.path.join(output_dir, png_filename)

            self.stdout.write(f'\n{"=" * 60}')
            self.stdout.write(f'{section_name}')

            doc = fitz.open(pdf_path)
            page = doc[0]
            zoom = RENDER_DPI / 72
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            pix.save(png_path)
            img_w, img_h = pix.width, pix.height

            gp = GRID_PARAMS.get(section_name, {})
            expected_spacing = gp.get('grid_pts')
            grid_info = detect_grid_from_pdf(page, expected_spacing=expected_spacing)
            if not grid_info:
                self.stdout.write(self.style.WARNING(f'Grid detection failed, using hardcoded params'))
                gp = GRID_PARAMS[section_name]
                gpts = gp['grid_pts']
                page_w, page_h = page.rect.width, page.rect.height
                grid_info = {
                    'h_positions': [round(gpts * i, 2) for i in range(int(page_h / gpts) + 2)],
                    'v_positions': [round(gpts * i, 2) for i in range(int(page_w / gpts) + 2)],
                    'grid_pts': gpts, 'grid_px': gp['grid_px'],
                    'origin_x_px': 0, 'origin_y_px': 0,
                    'floor_w_m': gp['v_count'] - 1, 'floor_h_m': gp['h_count'] - 1,
                }
            else:
                gp = GRID_PARAMS.get(section_name, {})
                expected_h_count = gp.get('h_count', 0)
                expected_v_count = gp.get('v_count', 0)
                if expected_h_count and expected_v_count:
                    h_ratio = len(grid_info['h_positions']) / expected_h_count
                    v_ratio = len(grid_info['v_positions']) / expected_v_count
                    self.stdout.write(f'  Grid ratios: h={h_ratio:.2f} ({len(grid_info["h_positions"])}/{expected_h_count}), v={v_ratio:.2f} ({len(grid_info["v_positions"])}/{expected_v_count})')
                    if h_ratio < 0.85 or v_ratio < 0.85:
                        gpts = gp['grid_pts']
                        page_w, page_h = page.rect.width, page.rect.height
                        grid_info = {
                            'h_positions': [round(gpts * i, 2) for i in range(int(page_h / gpts) + 2)],
                            'v_positions': [round(gpts * i, 2) for i in range(int(page_w / gpts) + 2)],
                            'grid_pts': gpts, 'grid_px': gp['grid_px'],
                            'origin_x_px': 0, 'origin_y_px': 0,
                            'floor_w_m': expected_v_count - 1, 'floor_h_m': expected_h_count - 1,
                        }
                        self.stdout.write(self.style.WARNING(
                            f'  Auto grid ratios too low, using hardcoded ({expected_v_count - 1}x{expected_h_count - 1}m)'))

            self.stdout.write(f'  Image: {img_w}x{img_h}px, Grid: {grid_info["grid_pts"]:.1f} pts/m = {grid_info["grid_px"]:.0f}px')
            self.stdout.write(f'  Floor: {grid_info["floor_w_m"]}x{grid_info["floor_h_m"]}m, h_pos: {len(grid_info["h_positions"])}, v_pos: {len(grid_info["v_positions"])}')

            regions = detect_regions(page, grid_info)
            doc.close()

            self.stdout.write(f'  Running OCR...')
            labels = run_ocr(png_path)
            self.stdout.write(f'  Found {len(labels)} stall labels via OCR')

            if section_name == 'North Plaza':
                gpts = grid_info['grid_pts']
                h_grid = grid_info['h_positions']
                v_grid = grid_info['v_positions']

                known_stalls = []
                matched_regions = set()
                for name, mx, my in NORTH_PLAZA_KNOWN_LABELS:
                    mx_px = mx * gpts * RENDER_DPI / 72
                    my_px = my * gpts * RENDER_DPI / 72

                    best_region = None
                    best_dist = float('inf')
                    for ri, region in enumerate(regions):
                        if ri in matched_regions:
                            continue
                        min_r, min_c = region['min_r'], region['min_c']
                        rcx_px = (v_grid[min_c] + region['width_m'] * gpts / 2) * RENDER_DPI / 72 if min_c < len(v_grid) else 0
                        rcy_px = (h_grid[min_r] + region['height_m'] * gpts / 2) * RENDER_DPI / 72 if min_r < len(h_grid) else 0
                        dist = ((rcx_px - mx_px) ** 2 + (rcy_px - my_px) ** 2) ** 0.5
                        if dist < best_dist:
                            best_dist = dist
                            best_region = ri

                    if best_region is not None and best_dist < gpts * RENDER_DPI / 72 * 4:
                        r = regions[best_region]
                        r['label'] = name
                        matched_regions.add(best_region)
                        self.stdout.write(f'    {name} -> region {best_region} ({r["width_m"]}x{r["height_m"]}m) dist={best_dist:.0f}px')

                known_name_set = {n for n, _, _ in NORTH_PLAZA_KNOWN_LABELS}
                known_stripped = {n.lstrip('0') for n in known_name_set}
                labels = [l for l in labels if l['text'] not in known_name_set and l['text'].lstrip('0') not in known_stripped]

            regions = match_labels_to_regions(regions, labels, grid_info)

            min_area = options['min_area']
            max_area = options['max_area']
            min_fill = options['min_fill']
            stalls = [r for r in regions if min_area <= r['area_m2'] <= max_area and r['fill'] >= min_fill]
            grey_count = len([r for r in regions if r.get('in_grey_fill')])

            size_dist = Counter()
            for s in stalls:
                size_dist[f"{s['width_m']}x{s['height_m']}m"] += 1
            labeled = len([s for s in stalls if s.get('label')])
            self.stdout.write(f'  Regions: {len(regions)}, Stalls: {len(stalls)}' +
                              (f' ({grey_count} in grey-fill zones)' if grey_count else '') +
                              f', Labeled: {labeled}/{len(stalls)}')
            for size, count in size_dist.most_common(10):
                self.stdout.write(f'    {size}: {count}')

            section, _ = FloorPlanSection.objects.update_or_create(
                event=event, name=section_name,
                defaults={
                    'display_order': display_order,
                    'original_width': img_w,
                    'original_height': img_h,
                    'original_pdf': matching_pdf,
                    'hall_width_meters': Decimal(str(grid_info['floor_w_m'])),
                    'hall_height_meters': Decimal(str(grid_info['floor_h_m'])),
                    'scale_factor': float(grid_info['grid_px']),
                    'notes': f'Grid: {grid_info["grid_pts"]:.1f} pts/m = {grid_info["grid_px"]:.0f}px, {grid_info["floor_w_m"]}x{grid_info["floor_h_m"]}m',
                }
            )

            with open(png_path, 'rb') as f:
                section.section_image.save(png_filename, File(f), save=True)

            h_positions = grid_info['h_positions']
            v_positions = grid_info['v_positions']
            gpts = grid_info['grid_pts']

            used_labels = set()
            for s in stalls:
                lbl = s.get('label')
                if lbl:
                    used_labels.add(lbl)

            if stalls:
                size_counts = Counter((s['width_m'], s['height_m']) for s in stalls)
                default_w, default_h = size_counts.most_common(1)[0][0]
            else:
                default_w, default_h = 3.0, 3.0

            unmatched_labels = [l for l in labels if l['text'] not in used_labels]
            orphan_re = re.compile(r'^(F\d{1,3}|FO\d+|NF\d+|J\d+|\d{1,3})$')
            filtered_unmatched = [l for l in unmatched_labels if orphan_re.match(l['text'].strip())]
            unmatched_labels = filtered_unmatched
            for lbl in unmatched_labels:
                col = int((lbl['cx'] / RENDER_DPI * 72 - v_positions[0]) / gpts)
                row = int((lbl['cy'] / RENDER_DPI * 72 - h_positions[0]) / gpts)
                col = max(0, min(col, len(v_positions) - 2))
                row = max(0, min(row, len(h_positions) - 2))
                stalls.append({
                    'min_r': row, 'min_c': col,
                    'width_m': default_w, 'height_m': default_h,
                    'area_m2': default_w * default_h, 'fill': 1.0,
                    'label': lbl['text'],
                    'orphan': True,
                })

            if unmatched_labels:
                self.stdout.write(f'  + {len(unmatched_labels)} orphan labels added as stalls')

            if section_name == 'North Plaza':
                np_blacklist_labels = {'35', '035', '46', '046', '646', '99', '099',
                                       '100', '0100', '404', '406', '846', '446'}
                np_blacklist_words = {'STOREROOM', 'STORE', 'EXT', 'ENTERTAINMENT', 'MARQUEE',
                                      'RIDE', 'VIP', 'BALLOON', 'SAUCER', 'CUP', 'BOAT',
                                      'FOOD', 'COURT', 'PARKING', 'FENCING', 'INFO',
                                      'ENTRANCE', 'DURBAN', 'SUMMER', 'SOUK', 'VENUE',
                                      'LAYOUT', 'COPYRIGHT', 'RESERVED', 'EXPO', 'SOLUTIONS',
                                      'THROUGH', 'PARTNERSHIP', 'KYLAMI', 'WESTMEAD', 'MIALNO',
                                      'MCGREGOR', 'BEACONVALE', 'PAARDEN', 'EILAND', 'AYANDA',
                                      'MZELEMU', 'AUGUST', 'CAPE', 'TOWN', 'JOHANNESBURG',
                                      'NORTH', 'PLAZA', 'DEC', 'CONNAUGHT', 'EXPORMES',
                                      'HEAVY', 'LIGHT', 'BOARDING', 'HOARDING', 'PLATFORM',
                                      'VARIATIONS', 'INDICATE', 'POSITIONS', 'NOTE', 'APPROX'}
                np_blacklist_numeric = {35, 46, 646, 99, 100, 404, 406, 846, 446}

                before = len(stalls)
                filtered = []
                for s in stalls:
                    lbl = s.get('label')
                    upper = (lbl or '').upper().strip()
                    if not lbl:
                        wm, hm = s['width_m'], s['height_m']
                        area = wm * hm
                        if area <= 25 and min(wm, hm) >= 2:
                            filtered.append(s)
                        continue
                    if any(bw in upper for bw in np_blacklist_words):
                        continue
                    if lbl in np_blacklist_labels:
                        continue
                    try:
                        if int(lbl) in np_blacklist_numeric:
                            continue
                    except (ValueError, TypeError):
                        pass
                    if not re.match(r'^(NF\d{1,3}|J\d{1,2}|\d{1,3})$', lbl):
                        continue
                    filtered.append(s)
                stalls = filtered
                self.stdout.write(f'  North Plaza: {before} -> {len(stalls)} stalls')
                for s in sorted(stalls, key=lambda x: (x.get('label') or '', x.get('min_r', 0))):
                    self.stdout.write(f'    {str(s.get("label") or "?"):8s} {s["width_m"]}x{s["height_m"]}m')

            seen_names = set()
            next_seq = 1
            for s in stalls:
                w_mm = s['width_m'] * 1000
                h_mm = s['height_m'] * 1000

                name = s.get('label')
                if name and name in seen_names:
                    name = None
                if name:
                    seen_names.add(name)
                else:
                    while f'{next_seq:03d}' in seen_names:
                        next_seq += 1
                    name = f'{next_seq:03d}'
                    seen_names.add(name)
                    next_seq += 1

                mr, mc = s['min_r'], s['min_c']
                pos_x = v_positions[mc] * 1000 / gpts if mc < len(v_positions) else 0
                pos_y = h_positions[mr] * 1000 / gpts if mr < len(h_positions) else 0

                Stall.objects.create(
                    event=event, section=section,
                    name=name,
                    stall_prefix='',
                    position_x=int(pos_x),
                    position_y=int(pos_y),
                    width=int(w_mm),
                    height=int(h_mm),
                    size_sqm=Decimal(str(s['width_m'] * s['height_m'])),
                    base_price=get_price(s['width_m'], s['height_m']),
                    status='available',
                )

            total_stalls += len(stalls)
            self.stdout.write(self.style.SUCCESS(f'  Created {len(stalls)} stalls'))

        self.stdout.write(self.style.SUCCESS(f'\nTotal: {total_stalls} stalls created'))
