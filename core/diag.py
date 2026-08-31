import io
from django.http import HttpResponse
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def diag(request):
    lines = []
    lines.append("DEBUG=%r" % settings.DEBUG)
    lines.append("ALLOWED_HOSTS=%r" % settings.ALLOWED_HOSTS)
    lines.append("USE_S3_STORAGE=%r" % getattr(settings, "USE_S3_STORAGE", None))
    lines.append("AKID len=%d" % len(settings.AWS_ACCESS_KEY_ID or ""))
    lines.append("SECRET len=%d" % len(settings.AWS_SECRET_ACCESS_KEY or ""))
    lines.append("CF_TOKEN len=%d" % len(settings.CLOUDFLARE_API_TOKEN or ""))
    lines.append("BUCKET=%r" % settings.AWS_STORAGE_BUCKET_NAME)
    lines.append("ENDPOINT=%r" % settings.AWS_S3_ENDPOINT_URL)
    lines.append("custom_domain=%r" % settings.AWS_S3_CUSTOM_DOMAIN)
    lines.append("STORAGES=%r" % settings.STORAGES["default"]["BACKEND"])
    try:
        from django.core.files.storage import default_storage
        name = default_storage.save("diag_probe.txt", io.BytesIO(b"probe"))
        lines.append("default_storage save OK name=%r" % name)
        lines.append("url=%s" % default_storage.url(name))
        default_storage.delete(name)
        lines.append("delete OK")
    except Exception as e:
        lines.append("STORAGE WRITE FAILED: %s" % e)
    return HttpResponse("\n".join(lines), content_type="text/plain")