# Al Ansaar ERP — Project Context

## Project Overview
Al Ansaar ERP is a Django-based event management system for managing exhibitions, trade shows, and events. It handles floor plan design, stall booking, invoicing, payments, exhibitor management, FNB banking integration, and accounting.

## Tech Stack
- **Backend**: Django 5.x, Python 3.12
- **Database**: PostgreSQL (on Render), SQLite locally
- **Frontend**: Bootstrap 5, vanilla JS, Django templates
- **Deployment**: Render (auto-deploy from `main` branch on GitHub)
- **Storage**: AWS S3 / Cloudflare R2 for media files
- **Email**: SMTP via mail.mogalia.co.za

---

## API Keys & Credentials

### Render
- **Service ID**: `srv-d9am9358nd3s73am9mc0`
- **Render API Key**: `rnd_l2KhiW0RbyKIG2XXf1oUAMLb2rJe`
- **Dashboard**: https://dashboard.render.com/web/srv-d9am9358nd3s73am9mc0
- **Production URL**: https://alansaar.site
- **GitHub Repo**: https://github.com/mogalia786/alansaar_erp (branch: `main`)

### FNB Banking (Sandbox)
- **FNB_CLIENT_ID**: `E84OOE`
- **FNB_CLIENT_SECRET**: `621NZsDknRDWjqf8sKhyH0ktjPXtbsr4`
- **FNB_BASE_URL**: `https://api.p.fnb.co.za/apigateway`
- **FNB_DEBTOR_ACCOUNT**: `63001731248`
- **FNB_DEBTOR_BRANCH**: `250655`

### Email (SMTP)
- **Host**: mail.mogalia.co.za
- **Port**: 465 (SSL)
- **User**: alansaar@mogalia.co.za
- **Password**: Faroq#786

---

## Deployment Commands

### Deploy via Render API
```powershell
$headers = @{ "Authorization" = "Bearer rnd_l2KhiW0RbyKIG2XXf1oUAMLb2rJe"; "Content-Type" = "application/json" }
$body = @{ "clearCache" = "clear" } | ConvertTo-Json
Invoke-RestMethod -Uri "https://api.render.com/v1/services/srv-d9am9358nd3s73am9mc0/deploys" -Headers $headers -Method POST -Body $body
```

### Check Deploy Status
```powershell
$headers = @{ "Authorization" = "Bearer rnd_l2KhiW0RbyKIG2XXf1oUAMLb2rJe" }
Invoke-RestMethod -Uri "https://api.render.com/v1/services/srv-d9am9358nd3s73am9mc0/deploys?limit=5" -Headers $headers
```

### Run Locally
```powershell
python manage.py runserver
```

---

## Key Architecture Notes

- `.env` is gitignored — Render env vars are set in `render.yaml` or Render dashboard
- Auto-deploy is ON — pushes to `main` trigger Render deploy
- Gunicorn uses `--timeout 120` to handle FNB API sync calls (previously caused 500 errors with default 30s timeout)
- `core/settings.py` has FNB defaults as fallback; Render env vars override them
- Floor plan editor is in `templates/portal/floor_plan.html` — fully client-side JS, stalls saved via AJAX POST to `save_stalls` endpoint
- **Floor plan unit convention**: Positions (x,y) are stored in **mm** in DB, converted to/from **pixels** using `scale_factor` (pixels/meter). Width/height are stored in **mm**, input from JS in **meters** (converted with `*1000`). NEVER use `scale_factor` for w/h conversion — only for x/y.

---

## Git Log (Recent)
```
a86034e Add gunicorn --timeout 120 to render.yaml; add deployment docs with Render API key
24a4d98 Revert FNB base URL back to api.p.fnb.co.za
0d6cdd5 Fix FNB base URL to api.fnb.co.za per docs
f47e7c5 Fix FNB base URL: api.i.fnb.co.za -> api.p.fnb.co.za
e0b6fc0 fix: RFQ detail 500 error when quotation has no provider
```

---

## PENDING: Floor Plan Editor — Drag/Move/Rotate/Rename/Rotate Tool

### Goal
Add a visual floor plan editor on the ERP portal page that allows admin to position angled stalls (Stand 1, Stand 2) by dragging, rotating, renaming directly on the PDF.

### Constraints
- Each grid cell on the PDF floor plans = 1 meter × 1 meter
- All stalls default to `available` status
- Dark grey blocks in PDF = non-stall areas (excluded)
- No prefix on Main Hall or East Lawn stall names
- Food stalls have `F`/`FO` prefix in PDF (e.g. F32, FO1)
- **Named areas (BAWAS, GINO, Bookshop, Jordanian Pavilion)** are group names for third-party purchased areas, NOT individual stall names
- **All OCR stall numbers must be preserved as-is**
- **Colored borders between stalls should be treated as borders** (stall dividers)
- **North Plaza exclusions from AGENTS.md**: Storeroom 2-5, Ext, Entertainment Marquee, Cup Ride, Boat Ride, VIP Marquee, Cup and Saucer, Balloon Ride, 099, 0100, 035, 46, 646, 004-013 — NOT stalls
- **North Plaza valid stalls from AGENTS.md**: NF1-NF20 (food court), NF21-NF23 (entrance marquee), Stands 1-18, J6-J8, Stalls 1-12 behind storeroom, parking bays
- **Keep stand names exactly like the original**
- Zoom via Ctrl+scroll, drag-to-pan, grid overlay
- Stall size = count of grid cells occupied
- Labels embedded in PDF as vector paths — not extractable as text objects

### What's Done (This Session)

#### 1. Stall.rotation field
- Added `rotation = models.IntegerField(default=0)` to `Stall` model
- Migration `0007_stall_rotation` created and applied

#### 2. AJAX endpoints (`events/views.py`)
- `stall_update(request, event_id, stall_id)` — POST to update position, size, name, rotation, price, or delete
- `stall_create(request, event_id)` — POST to create new stall (name, width_m, height_m, price, section_id, x, y in pixels)
- URL: `events/<int:event_id>/stall/<int:stall_id>/update/`
- URL: `events/<int:event_id>/stall/create/`
- **CRITICAL**: x/y positions from JS are in **pixels**, converted to mm with `* scale` where `scale = 1000/scale_factor`. Width/height from JS are in **meters**, converted to mm with `* 1000` (NOT `* scale`).

#### 3. ERP portal template (`templates/portal/floor_plan.html`)
- Edit Mode toggle button in toolbar
- Add Stall button → modal with name, width(m), height(m), price(ZAR)
- Drag-to-move stalls in edit mode (saves via AJAX)
- Right-click context menu: Rename, Edit Price, Rotate (prompts for angle), Resize, Delete
- Rotation applied via CSS `transform: rotate(Xdeg)`
- Stall data attributes: id, name, price, sq, w, h, status, zone, pw, ph, rot, bp
- Grid uses `SCALE` (scale_factor) for correct 1m spacing
- Stall font size: `Math.round(Math.min(s.w, s.h) * 0.4)`
- After add stall, scrolls to center on new stall
- After delete, updates stall/available counts

#### 4. Public floor plan template (`templates/events/floor_plan_view.html`)
- Same edit mode features as ERP portal (drag, rotate, rename, price, resize, delete, add stall)
- Same context menu, same AJAX endpoints

#### 5. ERP portal view (`portal/views.py`)
- Fixed stall coordinate scaling: now multiplies position by `scale_factor/1000` (was passing raw mm)
- Added `scale_factor` to `active_section` context dict
- Fixed grid in portal template: now uses `SCALE` (scale_factor) instead of hardcoded `1000`

#### 6. Stalls around storeroom 3/4 (user-confirmed original names)
  - 3 (was 036): x=118523 y=120238
  - 4 (was 021): x=118523 y=103238
  - 5 (was 014): x=117523 y=95238
  - 6 (was 011): x=117523 y=91238
  - 7: x=106300 y=84800 (created, 4×3m, 13 grids from storeroom left corner)
  - 1 and 2: NOT YET PLACED — user wants visual drag to position (both 4×3m, angled around storeroom 3)

### What's NOT Done / Pending

1. **Stands 1 and 2 placement**: Both are 4×3m, angled around storeroom 3. User needs to drag them into position using Edit Mode on the floor plan.
2. **Main Hall false positives**: 98 stalls in grey-fill zones (excluded from stall count) — these are likely incorrect detections
3. **East Lawn under-counting**: 36 stalls detected vs expected ~50+
4. **Dynamic Stand Pricing** (separate feature, detailed below)

---

## PENDING: Dynamic Stand Pricing Feature

### Goal
Replace all hardcoded stall prices, electricity deposit (R500), and VAT rate (15%) with configurable per-event values via a new `StallType` model.

### Constraints
- All existing defaults must be preserved (stall dimensions, aspect ratios)
- No existing functionality should break
- All new stall types/prices should be configurable per-event
- Do not change anything that breaks working features

### What to Implement

#### 1. StallType Model (`events/models.py`)
Add a new model after `Stall`:
```python
class StallType(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='stall_types')
    name = models.CharField(max_length=100)
    width_m = models.DecimalField(max_digits=5, decimal_places=2, help_text="Width in meters")
    height_m = models.DecimalField(max_digits=5, decimal_places=2, help_text="Height in meters")
    price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Base price in ZAR")
    prefix = models.CharField(max_length=20, default='Stand', help_text="Name prefix (Stand, Food, Kiddies)")
    border_color = models.CharField(max_length=20, blank=True, help_text="CSS color for toolbox border")
    is_default = models.BooleanField(default=False, help_text="System default type")
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['display_order', 'name']
        unique_together = ['event', 'name']

    def __str__(self):
        return f"{self.name} ({self.width_m}x{self.height_m}m) - R{self.price}"

    @property
    def size_sqm(self):
        return float(self.width_m * self.height_m)
```

#### 2. Event Model Fields (`events/models.py`)
Add to the `Event` model (after `max_stalls_per_exhibitor`):
```python
electricity_deposit = models.DecimalField(max_digits=8, decimal_places=2, default=500.00, help_text="Electricity deposit per stall requiring power")
vat_rate = models.DecimalField(max_digits=5, decimal_places=2, default=15.00, help_text="VAT rate as percentage (e.g. 15.00 for 15%%)")
```

#### 3. Data Migration
Create a data migration to seed default StallTypes for existing events:
- 3x3m Stand R5,000
- 3x4m Stand R6,500
- 3x6m Stand R9,000
- 2x3m Stand R3,500
- 4x3m Food R8,000 (orange border)
- 6x6m Kiddies R15,000 (blue border)

#### 4. Admin Registration (`events/admin.py`)
Register `StallType` in admin.

#### 5. Stall Type CRUD Views (`portal/views.py`)
Add JSON API views:
- `stall_types_json(request, event_id)` — returns all stall types for an event
- `create_stall_type(request, event_id)` — POST to create custom type
- `update_stall_type(request, event_id, type_id)` — POST to update
- `delete_stall_type(request, event_id, type_id)` — POST to delete (only non-default)

#### 6. URLs (`portal/urls.py`)
Add URL patterns:
```python
path('events/<int:event_id>/stall-types/', views.stall_types_json, name='stall_types_json'),
path('events/<int:event_id>/stall-types/create/', views.create_stall_type, name='create_stall_type'),
path('events/<int:event_id>/stall-types/<int:type_id>/update/', views.update_stall_type, name='update_stall_type'),
path('events/<int:event_id>/stall-types/<int:type_id>/delete/', views.delete_stall_type, name='delete_stall_type'),
```

#### 7. Floor Plan Template (`templates/portal/floor_plan.html`)
- Replace hardcoded 6 stall type cards (lines 104-127) with dynamic `{% for st in stall_types %}` loop
- Add "Add Custom Type" button + inline form below the list
- Pass `stall_types` and `event` context from `erp_floor_plan` view
- Update JS `addStall()` and drag-drop to use dynamic data attributes
- Add double-click-to-edit and delete on custom stall types
- Auto-load defaults from first active StallType for double-click empty canvas (line 420)

#### 8. Menu Rename (`templates/portal/base.html`)
- Change "Configuration" (line 68) to "Utilities"

#### 9. Replace Hardcoded Values
**Electricity deposit R500** (`bookings/views.py`):
- Line 98: `elec_dep = Decimal('500.00')` → use `event.electricity_deposit`
- Line 163: `elec_dep = Decimal('500.00')` → use `booking.event.electricity_deposit`

**VAT rate 15%**:
- `portal/views.py` line 770: `dr.booking.subtotal * Decimal('0.15')` → use `dr.booking.event.vat_rate / 100`
- `portal/views.py` line 968: `excl * Decimal('0.15')` → use event's vat_rate (need to pass event context)
- `bookings/views.py` line 100: `subtotal * Decimal('0.15')` → use `event.vat_rate / 100`
- `bookings/views.py` line 166: `booking.subtotal * Decimal('0.15')` → use `booking.event.vat_rate / 100`
- `bookings/views.py` line 186: `booking.subtotal * Decimal('0.15')` → use `booking.event.vat_rate / 100`

#### 10. View Context Update (`portal/views.py`)
Update `erp_floor_plan` (line 140) to pass `stall_types` to template:
```python
stall_types = event.stall_types.all().order_by('display_order', 'name')
# ... in render context:
'stall_types': stall_types,
```

#### 11. Migrations
- Run `python manage.py makemigrations events`
- Run `python manage.py migrate`
- Verify locally before pushing

---

## Critical Gotchas
- **Gunicorn timeout**: Must keep `--timeout 120` — FNB sync makes multiple API calls that take >30s
- **FNB URL**: Must be `api.p.fnb.co.za` (sandbox), NOT `api.i.fnb.co.za` or `api.fnb.co.za`
- **render.yaml email password**: Exposed in YAML (`Faroq#786`) — acceptable for this private repo
- **Floor plan editor**: Pure client-side JS — stalls are JS objects, only saved on explicit "Save" click
- **SVG floor plan**: Loaded from S3/R2 storage, falls back to local file, rendered as background

---

## File Reference (Key Files)
| File | Purpose |
|------|---------|
| `core/settings.py` | Django settings, FNB config (line 181-186) |
| `events/models.py` | Venue, Event, FloorPlan, Zone, Stall, AccessoryType models |
| `events/admin.py` | Admin registrations |
| `events/views.py` | Public floor plan view, stall_update AJAX, stall_create AJAX |
| `events/urls.py` | Public URL patterns including stall CRUD endpoints |
| `portal/views.py` | ERP dashboard, floor plan editor, booking management, expenses |
| `portal/urls.py` | All ERP URL patterns |
| `bookings/views.py` | Public-facing booking flow (book_stall, update_booking, add_accessory) |
| `templates/portal/base.html` | ERP sidebar navigation |
| `templates/portal/floor_plan.html` | ERP floor plan editor (JS-heavy, ~570 lines) with edit mode, add stall, drag, rotate, rename, price, resize, delete |
| `templates/events/floor_plan_view.html` | Public floor plan view (~600 lines) with same edit features |
| `render.yaml` | Render deployment config |
| `.env` | Local env vars (gitignored) |

---

## Current Stall Counts (Durban Summer Souk 2026)
- Main Hall: 424 stalls
- East Lawn: 36 stalls
- North Plaza: 103 stalls
- Total: 563 stalls
- Event ID: 1
- Floor Plan Section IDs: Main Hall=163, East Lawn=164, North Plaza=165

## North Plaza Stalls Around Storeroom 3/4 (user-confirmed original names)
- 3 (was 036): x=118523 y=120238
- 4 (was 021): x=118523 y=103238
- 5 (was 014): x=117523 y=95238
- 6 (was 011): x=117523 y=91238
- 7: x=106300 y=84800 (created, 4x3m)
- 1 and 2: NOT YET PLACED — user needs to visually drag into position (both 4x3m, angled around storeroom 3)

## Scale Factors
- Main Hall: 35 px/m, page: 4959x7009px
- East Lawn: 87.5 px/m, page: 9917x7017px
- North Plaza: 35 px/m, page: 4959x7009px
