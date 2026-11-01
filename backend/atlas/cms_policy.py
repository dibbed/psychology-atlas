"""Closed capability policy and the single boundary for auth-policy mutations."""
from contextlib import contextmanager

from django.contrib.auth.models import Group, Permission, User
from django.db import connection, transaction
from django.db.models import F, Q
from rest_framework.exceptions import APIException

from .cms_capabilities import CAPABILITIES, DELEGATIONS, KNOWN_PERMISSIONS
from .cms_models import AdminAuditEvent, RolePolicy


class CMSFailure(APIException):
    def __init__(self, code, status=403, message=None):
        self.status_code = status
        super().__init__({"code": code, "message": message or code})


def effective_permissions(user):
    # Always use a new user and current DB relations, never Django's per-instance permission cache.
    if not user or not user.is_authenticated:
        return set()
    user = User.objects.filter(pk=user.pk, is_active=True, is_staff=True).first()
    if user is None:
        return set()
    if user.is_superuser:
        return set(KNOWN_PERMISSIONS)
    result = set(Permission.objects.filter(
        Q(user=user) | Q(group__user=user), content_type__app_label="atlas",
        content_type__model="rolepolicy", codename__in=KNOWN_PERMISSIONS,
    ).values_list("codename", flat=True))
    return set(KNOWN_PERMISSIONS) if "cms_owner" in result else result


def require(user, capability):
    if capability not in KNOWN_PERMISSIONS or capability not in effective_permissions(user):
        raise CMSFailure("PERMISSION_DENIED")


def owners():
    return User.objects.filter(is_active=True, is_staff=True).filter(
        Q(is_superuser=True) |
        Q(user_permissions__content_type__app_label="atlas", user_permissions__content_type__model="rolepolicy", user_permissions__codename="cms_owner") |
        Q(groups__permissions__content_type__app_label="atlas", groups__permissions__content_type__model="rolepolicy", groups__permissions__codename="cms_owner")
    ).distinct()


@contextmanager
def policy_lock(expected=None):
    # SQLite's configured outer IMMEDIATE transaction and PostgreSQL's advisory lock share this boundary.
    if connection.vendor == "sqlite" and connection.settings_dict.get("OPTIONS", {}).get("transaction_mode") != "IMMEDIATE":
        raise CMSFailure("ROLE_LOCK_UNAVAILABLE", 503)
    with transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", [17001001])
        RolePolicy.objects.get_or_create(pk=1)
        policy = RolePolicy.objects.select_for_update().get(pk=1)
        if expected is not None and policy.version != expected:
            raise CMSFailure("STALE_REVISION", 412)
        yield policy


def grantable(user):
    held = effective_permissions(user)
    result = {c for c in CAPABILITIES if "cms_delegate_" + c[4:] in held}
    result |= held & DELEGATIONS
    if "cms_roles_grant_owner" in held:
        result |= {"cms_owner", "cms_roles_grant_owner"}
    return result


def permission_rows(codenames):
    if not isinstance(codenames, list) or any(not isinstance(c, str) or c not in KNOWN_PERMISSIONS for c in codenames):
        raise CMSFailure("INVALID_PERMISSIONS", 400)
    rows = list(Permission.objects.filter(content_type__app_label="atlas", content_type__model="rolepolicy", codename__in=codenames))
    if len(rows) != len(set(codenames)):
        raise CMSFailure("PERMISSION_UNAVAILABLE", 503)
    return rows


def group_permissions(group):
    rows = list(group.permissions.select_related("content_type"))
    if any(p.codename not in KNOWN_PERMISSIONS or p.content_type.app_label != "atlas" or p.content_type.model != "rolepolicy" for p in rows):
        return None
    return {p.codename for p in rows}


def visible_group(actor, group):
    caps = group_permissions(group)
    return caps is not None and caps <= grantable(actor)


def mutate_role(actor_id, kind, target_id, payload, expected, session_id):
    from .cms_sessions import current_session, consume_step_up, revoke_account

    with policy_lock(expected) as policy:
        actor = User.objects.get(pk=actor_id)
        current_session(session_id, actor)
        require(actor, "cms_roles_edit")
        authority = effective_permissions(actor)
        ceiling = grantable(actor)
        before_owners = set(owners().values_list("pk", flat=True))
        sensitive = False
        if kind == "user":
            if set(payload) - {"permissions", "groups", "is_active", "is_staff", "is_superuser"}:
                raise CMSFailure("INVALID_FIELDS", 400)
            target = User.objects.select_for_update().filter(pk=target_id).first()
            if target is None:
                raise CMSFailure("NOT_FOUND", 404)
            if "permissions" in payload:
                rows = permission_rows(payload["permissions"])
                before = set(target.user_permissions.filter(content_type__app_label="atlas", content_type__model="rolepolicy").values_list("codename", flat=True))
                changed = before ^ set(payload["permissions"])
                if not changed <= ceiling:
                    raise CMSFailure("DELEGATION_DENIED")
                sensitive |= bool(changed & {"cms_owner", "cms_roles_grant_owner"})
                # Only CMS permissions are replaced; unrelated existing application permissions are preserved.
                target.user_permissions.remove(*target.user_permissions.filter(content_type__app_label="atlas", content_type__model="rolepolicy"))
                target.user_permissions.add(*rows)
            if "groups" in payload:
                ids = payload["groups"]
                if not isinstance(ids, list) or any(type(i) is not int or i <= 0 for i in ids):
                    raise CMSFailure("INVALID_GROUPS", 400)
                selected = list(Group.objects.select_for_update().filter(pk__in=ids))
                existing = list(target.groups.all())
                changed_groups = [g for g in selected + existing if (g.pk in ids) != (g in existing)]
                if len(selected) != len(set(ids)) or any(not visible_group(actor, g) for g in changed_groups):
                    raise CMSFailure("NOT_FOUND", 404)
                sensitive |= any(bool(group_permissions(g) & {"cms_owner", "cms_roles_grant_owner"}) for g in changed_groups)
                target.groups.set(selected)
            for field in ("is_active", "is_staff", "is_superuser"):
                if field in payload:
                    if type(payload[field]) is not bool:
                        raise CMSFailure("INVALID_FIELDS", 400)
                    require(actor, "cms_roles_grant_owner")
                    sensitive |= getattr(target, field) != payload[field]
                    setattr(target, field, payload[field])
            target.save(update_fields=("is_active", "is_staff", "is_superuser"))
            sensitive |= target.pk in before_owners and target.pk not in set(owners().values_list("pk", flat=True))
        elif kind in {"group", "delete_group", "create_group"}:
            if kind == "create_group":
                if set(payload) != {"name", "permissions"} or not isinstance(payload["name"], str) or not 1 <= len(payload["name"].strip()) <= 150:
                    raise CMSFailure("INVALID_FIELDS", 400)
                if Group.objects.filter(name=payload["name"].strip()).exists():
                    raise CMSFailure("GROUP_EXISTS", 409)
                target = Group.objects.create(name=payload["name"].strip())
                before = set()
            else:
                target = Group.objects.select_for_update().filter(pk=target_id).first()
                if target is None or not visible_group(actor, target):
                    raise CMSFailure("NOT_FOUND", 404)
                before = group_permissions(target)
            if kind == "delete_group":
                if payload:
                    raise CMSFailure("INVALID_FIELDS", 400)
                changed = before
            else:
                if kind == "group" and set(payload) != {"permissions"}:
                    raise CMSFailure("INVALID_FIELDS", 400)
                rows = permission_rows(payload["permissions"])
                changed = before ^ set(payload["permissions"])
            if not changed <= ceiling:
                raise CMSFailure("DELEGATION_DENIED")
            sensitive = bool(changed & {"cms_owner", "cms_roles_grant_owner"})
            if kind == "delete_group":
                target.delete()
            else:
                target.permissions.set(rows)
        else:
            raise CMSFailure("INVALID_ACTION", 400)
        if not owners().exists():
            raise CMSFailure("LAST_OWNER", 409)
        if sensitive:
            # The policy lock preserves authority during this operation, including self-demotion.
            if "cms_roles_grant_owner" not in authority:
                raise CMSFailure("PERMISSION_DENIED")
            consume_step_up(session_id, actor, kind, target_id, payload)
        if kind == "user" and not (target.is_active and target.is_staff):
            revoke_account(target)
        changed = RolePolicy.objects.filter(pk=1, version=policy.version).update(version=F("version") + 1)
        if changed != 1:
            raise CMSFailure("STALE_REVISION", 412)
        AdminAuditEvent.objects.create(actor=actor, target_id=target.pk if kind == "create_group" else target_id, action="roles." + kind, outcome="success",
            target_kind="user" if kind == "user" else "group", base_revision=policy.version,
            new_revision=policy.version + 1, policy_version=policy.version, diff=sorted(set(payload) & {"permissions", "groups", "is_active", "is_staff", "is_superuser"}))
        return policy.version + 1
