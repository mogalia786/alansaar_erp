from django.conf import settings
from django.http import HttpResponse


class MaxBodySizeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        limit = getattr(settings, 'MAX_UPLOAD_SIZE', 25 * 1024 * 1024)
        cl = request.META.get('CONTENT_LENGTH')
        if cl and request.method in ('POST', 'PUT', 'PATCH'):
            try:
                if int(cl) > limit:
                    return HttpResponse(
                        'Request body too large (max 25MB).',
                        status=413,
                        content_type='text/plain',
                    )
            except ValueError:
                pass
        return self.get_response(request)