import base64
import io
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage


# Base64-encoded floor plan PNG images
IMAGES = {
    'floor_plan_sections/1_main_hall_Oz2k97q.png': None,
    'floor_plan_sections/1_east_lawn_EfYF7ud.png': None,
    'floor_plan_sections/1_north_plaza_N3e1J9d.png': None,
}


class Command(BaseCommand):
    help = 'Upload floor plan section images to storage'

    def add_arguments(self, parser):
        parser.add_argument('--generate', action='store_true', help='Generate placeholder images instead')

    def handle(self, *args, **options):
        if options['generate']:
            self.generate_placeholders()
        else:
            self.upload_existing()

    def upload_existing(self):
        import os
        from django.conf import settings
        for key in IMAGES:
            local_path = os.path.join(str(settings.MEDIA_ROOT), key)
            if os.path.exists(local_path):
                self.stdout.write(f'Uploading {key}...')
                with open(local_path, 'rb') as f:
                    content = f.read()
                saved_name = default_storage.save(key, ContentFile(content))
                self.stdout.write(self.style.SUCCESS(f'  Saved as {saved_name}'))
            else:
                self.stdout.write(self.style.WARNING(f'  Not found locally: {local_path}'))

    def generate_placeholders(self):
        from PIL import Image, ImageDraw, ImageFont
        sections = {
            'floor_plan_sections/1_main_hall_Oz2k97q.png': (4959, 7009, 'Main Hall'),
            'floor_plan_sections/1_east_lawn_EfYF7ud.png': (9917, 7017, 'East Lawn'),
            'floor_plan_sections/1_north_plaza_N3e1J9d.png': (4959, 7009, 'North Plaza'),
        }
        for key, (w, h, label) in sections.items():
            self.stdout.write(f'Generating {key} ({w}x{h})...')
            img = Image.new('RGB', (w, h), color=(240, 240, 240))
            draw = ImageDraw.Draw(img)
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 120)
            except Exception:
                font = ImageFont.load_default()
            bbox = draw.textbbox((0, 0), label, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(((w - tw) // 2, (h - th) // 2), label, fill=(200, 200, 200), font=font)
            buf = io.BytesIO()
            img.save(buf, format='PNG', optimize=True)
            saved_name = default_storage.save(key, ContentFile(buf.getvalue()))
            self.stdout.write(self.style.SUCCESS(f'  Saved as {saved_name}'))
