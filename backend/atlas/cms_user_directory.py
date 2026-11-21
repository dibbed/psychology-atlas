"""P14 minimal user directory. No secrets, private progress or impersonation."""
from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework.response import Response

from .cms_policy import CMSFailure, effective_permissions, policy_lock, require
from .cms_views import AdminAPIView, page


def _public_row(user):
    return {
        "id": user.pk, "username": user.username,
        "is_active": user.is_active, "is_staff": user.is_staff,
    }


class CMSUserDirectoryView(AdminAPIView):
    capability = "cms_user_view"

    def get(self, request):
        with policy_lock():
            require(request.user, "cms_user_view")
            q = request.query_params.get("q", "").strip()
            if len(q) > 200 or request.query_params.getlist("q") != (
                [request.query_params["q"]] if "q" in request.query_params else []
            ):
                raise CMSFailure("INVALID_QUERY", 400)
            rows = get_user_model().objects.all()
            if q:
                condition = Q(username__icontains=q)
                if q.isascii() and q.isdigit() and len(q) < 19:
                    condition |= Q(pk=int(q))
                rows = rows.filter(condition)
            meta, selection = page(request, rows.order_by("pk"), extra=("q",))
            return Response({**meta, "results": [_public_row(user) for user in selection]})


class CMSUserDetailView(AdminAPIView):
    capability = "cms_user_view"

    def get(self, request, user_id):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        with policy_lock():
            require(request.user, "cms_user_view")
            user = get_user_model().objects.filter(pk=user_id).first()
            if user is None:
                raise CMSFailure("NOT_FOUND", 404)
            result = _public_row(user)
            if "cms_roles_view" in effective_permissions(request.user):
                # Effective capabilities only; no raw credentials, identities
                # of other privileged users or group membership objects.
                result["effective_permissions"] = sorted(effective_permissions(user))
            return Response(result)
