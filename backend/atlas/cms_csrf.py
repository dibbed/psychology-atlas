from django.http import JsonResponse
from django.views.csrf import csrf_failure


def failure(request, reason=""):
    if request.path.startswith(("/api/admin/", "/account/", "/admin/")):
        response = JsonResponse({"code": "CSRF_FAILED", "message": "CSRF verification failed"}, status=403)
        response["Cache-Control"] = "no-store"
        return response
    return csrf_failure(request, reason)
