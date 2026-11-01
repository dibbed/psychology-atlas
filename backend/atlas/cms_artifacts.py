"""Private archives/intake. Physical cleanup is Windows-handle-only; other platforms fail closed."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
from datetime import timedelta
import unicodedata
import uuid

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import CommandError
from django.db import connection
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify

from .assessment_publication import (SCHEMA as ASSESSMENT_SCHEMA, archive_fields,
    parse_document as parse_assessment, protected_paths)
from .cms_audit import attribution
from .cms_content import digest
from .cms_job_models import AdminArtifact, AdminJob, ResearchRecordDecision
from .cms_models import AdminAuditEvent
from .cms_policy import CMSFailure, effective_permissions, policy_lock, require
from .cms_sessions import current_session
from .management.commands.import_research_datasets import Command as ResearchImporter, LIST_SECTIONS
from .models import ResearchDataset, ResearchRecord

MAX_BYTES = 25 * 1024 * 1024
MAX_RECORDS = 50000
MAX_DEPTH = 64
MAX_STRING = 100000
MAX_NODES = 1000000
MAX_EVIDENCE_BYTES = 65536
KINDS = {"research_json": "research", "dsm_json": "dsm", "assessment_json": "assessment"}
PURPOSES = {"research_review", "source_review", "rights_review", "intake_validation"}


def _uuid(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        raise CMSFailure("NOT_FOUND", 404)


def _link(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _root(create=False):
    configured = getattr(settings, "CMS_ARTIFACT_ROOT", None)
    if not configured or not Path(configured).is_absolute():
        raise CMSFailure("ARTIFACT_STORAGE_UNAVAILABLE", 503)
    root = Path(os.path.abspath(configured))
    public = [getattr(settings, name, None) for name in ("MEDIA_ROOT", "STATIC_ROOT")]
    public.append(Path(settings.BASE_DIR).parent / "frontend" / "public")
    if any(root.is_relative_to(Path(p).absolute()) for p in public if p):
        raise CMSFailure("ARTIFACT_STORAGE_UNAVAILABLE", 503)
    for part in (*reversed(root.parents), root):
        try:
            info = part.lstat()
        except FileNotFoundError:
            if not create:
                raise CMSFailure("ARTIFACT_UNAVAILABLE", 409)
            continue
        if _link(info) or not stat.S_ISDIR(info.st_mode):
            raise CMSFailure("ARTIFACT_STORAGE_UNAVAILABLE", 503)
    if create:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        return _root()
    return root


def _path(artifact):
    if artifact.storage_key != artifact.pk.hex + ".json":
        raise CMSFailure("ARTIFACT_INTEGRITY", 409)
    return _root() / artifact.storage_key


def artifact_bytes(artifact):
    """Read an immutable, bounded regular file without following links."""
    if type(artifact.size) is not int or not 0 < artifact.size <= MAX_BYTES:
        raise CMSFailure("ARTIFACT_INTEGRITY", 409)
    try:
        path = _path(artifact)
        before = path.lstat()
        if _link(before) or not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size != artifact.size:
            raise CMSFailure("ARTIFACT_INTEGRITY", 409)
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if (opened.st_dev, opened.st_ino, opened.st_size) != (before.st_dev, before.st_ino, before.st_size):
                raise CMSFailure("ARTIFACT_INTEGRITY", 409)
            raw = stream.read(MAX_BYTES + 1)
            after = os.fstat(stream.fileno())
        if (after.st_size != artifact.size or len(raw) != artifact.size
                or hashlib.sha256(raw).hexdigest() != artifact.sha256):
            raise CMSFailure("ARTIFACT_INTEGRITY", 409)
        return raw
    except OSError:
        raise CMSFailure("ARTIFACT_UNAVAILABLE", 409)


def artifact_scope(actor, artifact, download=False):
    held = effective_permissions(actor)
    reviewer = False
    if artifact.kind == "evidence_json":
        from .cms_governance import entry, resource_binding
        if artifact.domain != entry(artifact.resource_type)[1]:
            raise CMSFailure("NOT_FOUND", 404)
        if "cms_" + artifact.domain + "_view" not in held:
            raise CMSFailure("NOT_FOUND", 404)
        binding = resource_binding(artifact.resource_type, artifact.resource_id)
        if binding["resource_version"] != artifact.resource_version:
            raise CMSFailure("NOT_FOUND", 404)
        reviewer = "cms_artifact_download" in held and any({"cms_" + kind + "_decide",
            "cms_review_decide_" + artifact.domain + "_" + kind} <= held for kind in ("rights", "terminology"))
    elif artifact.kind not in KINDS or artifact.domain != KINDS[artifact.kind]:
        raise CMSFailure("NOT_FOUND", 404)
    elif "cms_" + artifact.domain + "_view" not in held:
        raise CMSFailure("NOT_FOUND", 404)
    if artifact.owner_id != actor.pk and "cms_owner" not in held and not reviewer:
        raise CMSFailure("NOT_FOUND", 404)
    require(actor, "cms_enter")
    require(actor, "cms_" + artifact.domain + "_view")
    if download:
        require(actor, "cms_artifact_download")
    elif artifact.kind in KINDS:
        require(actor, "cms_research_intake" if artifact.domain == "research" else "cms_" + artifact.domain + "_edit")


def get_artifact(actor, artifact_id, download=False, lock=False):
    rows = AdminArtifact.objects.select_for_update() if lock else AdminArtifact.objects
    artifact = rows.filter(pk=_uuid(artifact_id)).first()
    if artifact is None:
        raise CMSFailure("NOT_FOUND", 404)
    artifact_scope(actor, artifact, download)
    if download and (artifact.state != "ready" or artifact.expires_at <= timezone.now()):
        raise CMSFailure("ARTIFACT_NOT_READY", 409)
    return artifact


def artifact_data(artifact):
    data = {key: (str(artifact.pk) if key == "id" else getattr(artifact, key)) for key in (
        "id", "kind", "domain", "resource_type", "resource_id", "resource_version", "filename", "sha256", "size",
        "state", "version", "expires_at", "purged_at", "validation_code", "created_at")}
    if artifact.state != "revoked" and artifact.expires_at <= timezone.now():
        data["state"] = "expired"
    data["cleanup_supported"] = cleanup_supported()
    return data


def evidence_snapshot(artifact_ids, resource_type, resource_id, resource_version, lock=False):
    """Stable exact-scope bindings only; readiness is never a rights attestation."""
    if (not isinstance(artifact_ids, list) or len(artifact_ids) > 100
            or type(resource_id) is not int or not 0 < resource_id < 2**63
            or type(resource_version) is not str or not 0 < len(resource_version) <= 500):
        raise CMSFailure("INVALID_EVIDENCE", 400)
    from .cms_governance import entry
    domain = entry(resource_type)[1]
    try:
        ids = sorted({uuid.UUID(str(value)) for value in artifact_ids}, key=str)
    except (ValueError, TypeError, AttributeError):
        raise CMSFailure("INVALID_EVIDENCE", 400)
    if len(ids) != len(artifact_ids):
        raise CMSFailure("INVALID_EVIDENCE", 400)
    rows = AdminArtifact.objects.filter(pk__in=ids).order_by("pk")
    if lock:
        rows = rows.select_for_update()
    found = {row.pk: row for row in rows}
    result = []
    for artifact_id in ids:
        row = found.get(artifact_id)
        if row is None or (row.kind, row.resource_type, row.resource_id, row.resource_version) != (
                "evidence_json", resource_type, resource_id, resource_version):
            raise CMSFailure("INVALID_EVIDENCE", 400)
        if row.domain != domain:
            raise CMSFailure("INVALID_EVIDENCE", 400)
        if row.state != "ready" or row.expires_at <= timezone.now():
            raise CMSFailure("ARTIFACT_NOT_READY", 409)
        if row.validation_code != "JSON_VALID" or row.size > MAX_EVIDENCE_BYTES:
            raise CMSFailure("ARTIFACT_INTEGRITY", 409)
        artifact_bytes(row)
        result.append({"id": str(row.pk), "resource_type": row.resource_type, "resource_id": row.resource_id,
            "resource_version": row.resource_version, "sha256": row.sha256, "size": row.size,
            "version": row.version, "state": row.state, "ready": True, "validation_code": row.validation_code,
            "expires_at": row.expires_at.isoformat()})
    return result


def audit(actor, action, reason, request_id, *, artifact=None, record=None, policy=None):
    AdminAuditEvent.objects.create(actor=actor, action=action, outcome="success", reason=reason,
        request_id=request_id, target_key=str(artifact.pk) if artifact else "",
        target_id=record.pk if record else None, policy_version=policy.version if policy else None)


def _write_authority(actor_id, session_id):
    actor = User.objects.get(pk=actor_id)
    current_session(session_id, actor)
    require(actor, "cms_artifact_upload")
    return actor


def _edit_scope(actor, artifact):
    artifact_scope(actor, artifact)
    if artifact.kind == "evidence_json":
        require(actor, "cms_" + artifact.domain + "_edit")


def upload_artifact(actor_id, session_id, upload, kind, resource_type, resource_id, resource_version, request_id):
    if type(kind) is not str or kind not in {*KINDS, "evidence_json"}:
        raise CMSFailure("UNSUPPORTED_SCHEMA", 400)
    artifact = AdminArtifact(id=uuid.uuid4(), kind=kind, domain=KINDS.get(kind, ""),
        resource_type=resource_type or "", resource_id=resource_id, resource_version=resource_version or "")
    if kind != "evidence_json" and (resource_type or resource_id is not None or resource_version):
        raise CMSFailure("INVALID_SCOPE", 400)
    if kind == "evidence_json":
        from .cms_governance import entry
        artifact.domain = entry(resource_type)[1]
        if (type(resource_id) is not int or resource_id <= 0 or type(resource_version) is not str
                or not 0 < len(resource_version) <= 500):
            raise CMSFailure("INVALID_SCOPE", 400)
    artifact.owner_id = actor_id
    with policy_lock():
        _edit_scope(_write_authority(actor_id, session_id), artifact)
    if (upload is None or not hasattr(upload, "chunks") or type(upload.size) is not int
            or not 0 < upload.size <= MAX_BYTES or upload.content_type not in {"application/json", "text/json"}):
        raise CMSFailure("INVALID_UPLOAD", 400)
    filename = str(upload.name).replace("\\", "/").split("/")[-1]
    filename = "".join(c for c in filename if not unicodedata.category(c).startswith("C"))[:120]
    if not filename.lower().endswith(".json"):
        raise CMSFailure("INVALID_UPLOAD", 400)
    artifact.filename = filename
    artifact.storage_key = artifact.pk.hex + ".json"
    path = _root(create=True) / artifact.storage_key
    total, checksum = 0, hashlib.sha256()
    created = False
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
        created = True
        with os.fdopen(fd, "wb") as stream:
            for chunk in upload.chunks(65536):
                total += len(chunk)
                if total > MAX_BYTES:
                    raise CMSFailure("UPLOAD_TOO_LARGE", 400)
                stream.write(chunk)
                checksum.update(chunk)
            stream.flush()
            os.fsync(stream.fileno())
        if total != upload.size:
            raise CMSFailure("INVALID_UPLOAD", 400)
        with policy_lock() as policy:
            actor = _write_authority(actor_id, session_id)
            _edit_scope(actor, artifact)
            artifact.owner_ref = attribution(actor_id)
            artifact.sha256, artifact.size = checksum.hexdigest(), total
            # Access expiry is separate from explicit, dependency-aware byte cleanup.
            artifact.expires_at = timezone.now() + timedelta(days=7)
            artifact.save(force_insert=True)
            audit(actor, "artifact.upload", "ARTIFACT_UPLOAD", request_id, artifact=artifact, policy=policy)
        return artifact
    except BaseException:
        if created:
            path.unlink(missing_ok=True)
        raise


def _cleanup_platform():
    if sys.platform != "win32":
        raise CMSFailure("CLEANUP_PLATFORM_UNAVAILABLE", 503)


def cleanup_supported():
    """Only the Windows handle adapter is implemented; POSIX has no safe leaf adapter."""
    try:
        _WindowsCleanup()
    except CMSFailure:
        return False
    return True


class _WindowsCleanup:
    """Pin every directory and the verified leaf; deletion is by handle, never pathname."""

    def __init__(self):
        _cleanup_platform()
        import ctypes
        from ctypes import wintypes as w
        self.c = ctypes
        self.handles = []

        class FileInfo(ctypes.Structure):
            _fields_ = [("attributes", w.DWORD), ("created", w.FILETIME), ("accessed", w.FILETIME),
                ("written", w.FILETIME), ("device", w.DWORD), ("size_high", w.DWORD),
                ("size_low", w.DWORD), ("links", w.DWORD), ("index_high", w.DWORD), ("index_low", w.DWORD)]

        self.FileInfo = FileInfo
        try:
            self.api = ctypes.WinDLL("kernel32", use_last_error=True)
            signatures = {
                "CreateFileW": ([w.LPCWSTR, w.DWORD, w.DWORD, w.LPVOID, w.DWORD, w.DWORD, w.HANDLE], w.HANDLE),
                "GetFileInformationByHandle": ([w.HANDLE, ctypes.POINTER(FileInfo)], w.BOOL),
                "ReadFile": ([w.HANDLE, w.LPVOID, w.DWORD, ctypes.POINTER(w.DWORD), w.LPVOID], w.BOOL),
                "SetFileInformationByHandle": ([w.HANDLE, ctypes.c_int, w.LPVOID, w.DWORD], w.BOOL),
                "CloseHandle": ([w.HANDLE], w.BOOL),
            }
            for name, (arguments, result) in signatures.items():
                function = getattr(self.api, name)
                function.argtypes, function.restype = arguments, result
        except (AttributeError, OSError):
            raise CMSFailure("CLEANUP_PLATFORM_UNAVAILABLE", 503)

    def _info(self, handle):
        info = self.FileInfo()
        if not self.api.GetFileInformationByHandle(handle, self.c.byref(info)):
            raise CMSFailure("ARTIFACT_INTEGRITY", 409)
        return info

    def _open(self, path, access, directory):
        # OPEN_EXISTING; BACKUP_SEMANTICS | OPEN_REPARSE_POINT; share READ only.
        handle = self.api.CreateFileW(str(path), access, 1, None, 3, 0x02200000, None)
        if handle == self.c.c_void_p(-1).value:
            raise CMSFailure("ARTIFACT_UNAVAILABLE", 409)
        self.handles.append(handle)
        info = self._info(handle)
        try:
            current = path.lstat()
        except OSError:
            raise CMSFailure("ARTIFACT_UNAVAILABLE", 409)
        if (info.attributes & 0x400 or bool(info.attributes & 0x10) != directory
                or _link(current) or not (stat.S_ISDIR(current.st_mode) if directory else stat.S_ISREG(current.st_mode))
                or (current.st_dev & 0xffffffff, current.st_ino)
                != (info.device, (info.index_high << 32) | info.index_low)):
            raise CMSFailure("ARTIFACT_INTEGRITY", 409)
        return handle, info, {"dev": current.st_dev, "ino": current.st_ino}

    def __enter__(self):
        try:
            self.root = _root()
            before = self.root.lstat()
            for part in (*reversed(self.root.parents), self.root):
                _, _, identity = self._open(part, 0x80, True)  # FILE_READ_ATTRIBUTES
            self.identity = identity
            if self.identity != {"dev": before.st_dev, "ino": before.st_ino}:
                raise CMSFailure("ARTIFACT_INTEGRITY", 409)
            return self
        except OSError:
            self.__exit__(None, None, None)
            raise CMSFailure("ARTIFACT_UNAVAILABLE", 409)
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        failed = False
        while self.handles:
            if not self.api.CloseHandle(self.handles.pop()):
                failed = True
        if failed:
            raise CMSFailure("ARTIFACT_STORAGE_UNAVAILABLE", 503)

    def file(self, artifact, expected=None):
        path = _path(artifact)
        if path.parent != self.root:
            raise CMSFailure("CHECKPOINT_INTEGRITY", 409)
        handle, info, identity = self._open(path, 0x80010000, False)  # GENERIC_READ | DELETE
        if (info.links != 1 or ((info.size_high << 32) | info.size_low) != artifact.size
                or expected is not None and identity != expected):
            raise CMSFailure("ARTIFACT_INTEGRITY", 409)
        total, checksum = 0, hashlib.sha256()
        buffer, count = self.c.create_string_buffer(65536), self.c.c_ulong()
        while True:
            if not self.api.ReadFile(handle, buffer, len(buffer), self.c.byref(count), None):
                raise CMSFailure("ARTIFACT_UNAVAILABLE", 409)
            if not count.value:
                break
            total += count.value
            if total > MAX_BYTES or total > artifact.size:
                raise CMSFailure("ARTIFACT_INTEGRITY", 409)
            checksum.update(buffer.raw[:count.value])
        after = self._info(handle)
        stable = ("attributes", "device", "links", "size_high", "size_low", "index_high", "index_low")
        if (total != artifact.size or checksum.hexdigest() != artifact.sha256
                or any(getattr(info, name) != getattr(after, name) for name in stable)
                or (info.written.dwLowDateTime, info.written.dwHighDateTime)
                != (after.written.dwLowDateTime, after.written.dwHighDateTime)):
            raise CMSFailure("ARTIFACT_INTEGRITY", 409)
        return handle, identity

    def delete(self, handle):
        disposition = self.c.c_ubyte(1)  # FILE_DISPOSITION_INFO.DeleteFile = TRUE
        if not self.api.SetFileInformationByHandle(handle, 4, self.c.byref(disposition), self.c.sizeof(disposition)):
            raise CMSFailure("ARTIFACT_UNAVAILABLE", 409)


def cleanup_eligible(artifact):
    """Expiry permits explicit cleanup only while no historical consumer needs the bytes."""
    if artifact.purged_at is not None:
        raise CMSFailure("ARTIFACT_RETENTION_HOLD", 409)
    if artifact.expires_at > timezone.now():
        raise CMSFailure("ARTIFACT_NOT_EXPIRED", 409)
    if (ResearchDataset.objects.filter(source_sha256=artifact.sha256).exists()
            or AdminJob.objects.filter(kind="research_intake", artifact__sha256=artifact.sha256,
                status__in=("queued", "running", "reconciling", "succeeded")).exists()):
        raise CMSFailure("ARTIFACT_RETENTION_HOLD", 409)
    from .cms_governance_models import GovernanceRevision
    # SQLite has no JSON containment; inspect both fields in every immutable revision.
    for payload in GovernanceRevision.objects.values_list("payload", flat=True).iterator():
        if any(isinstance(item, dict) and item.get("artifact_id") == str(artifact.pk)
                for field in ("evidence", "holder_evidence") for item in payload.get(field, [])):
            raise CMSFailure("ARTIFACT_RETENTION_HOLD", 409)
    if not cleanup_supported():
        raise CMSFailure("CLEANUP_PLATFORM_UNAVAILABLE", 503)


def _cleanup_target(job):
    """Validate the committed intent before either deletion or metadata-only recovery."""
    from .cms_jobs import artifact_digest, job_scope
    try:
        artifact = AdminArtifact.objects.select_for_update().get(pk=job.artifact_id)
        checkpoint = job.checkpoint
        if (job.kind != "artifact_cleanup" or not isinstance(checkpoint, dict)
                or checkpoint.get("cleanup_prepared") is not True
                or checkpoint.get("complete", False) is not False
                or type(checkpoint.get("artifact_version")) is not int
                or checkpoint["artifact_version"] != artifact.version
                or checkpoint.get("sha256") != artifact.sha256
                or not re.fullmatch(r"[0-9a-f]{64}", artifact.sha256)
                or type(checkpoint.get("size")) is not int or checkpoint["size"] != artifact.size
                or not 0 < artifact.size <= MAX_BYTES
                or job.payload_digest != artifact_digest(artifact, job.kind)
                or job.actor_id is None or job.actor_ref != attribution(job.actor_id)
                or type(job.progress_done) is not int or job.progress_done != 0
                or type(job.progress_total) is not int or job.progress_total != 1):
            raise CMSFailure("CHECKPOINT_INTEGRITY", 409)
        job_scope(job.actor, job)
        cleanup_eligible(artifact)
        path = _path(artifact)
        directory = path.parent.lstat()
        identity = checkpoint.get("directory_identity")
        if (checkpoint.get("storage_profile") != digest(str(path.parent))
                or not isinstance(identity, dict) or set(identity) != {"dev", "ino"}
                or any(type(value) is not int for value in identity.values())
                or identity != {"dev": directory.st_dev, "ino": directory.st_ino}
                or not isinstance(checkpoint.get("file_identity"), dict)
                or set(checkpoint["file_identity"]) != {"dev", "ino"}
                or any(type(value) is not int for value in checkpoint["file_identity"].values())):
            raise CMSFailure("CHECKPOINT_INTEGRITY", 409)
        return artifact, path
    except (CMSFailure, OSError, AdminArtifact.DoesNotExist):
        raise CMSFailure("CHECKPOINT_INTEGRITY", 409)


def _cleanup_receipt(job, artifact):
    artifact.state, artifact.purged_at = "expired", timezone.now()
    artifact.version += 1
    artifact.save(update_fields=("state", "purged_at", "version"))
    job.checkpoint = {**job.checkpoint, "complete": True}
    job.progress_done = job.progress_total = 1
    audit(job.actor, "artifact.cleanup", "ARTIFACT_CLEANUP", uuid.uuid4(), artifact=artifact)
    return {"artifact_id": str(artifact.pk), "cleaned": True}


def process_cleanup(job_id, lease_token):
    from .cms_jobs import audit as job_audit, checkpoint_job
    # Authority and lease are checked before any private storage inspection.
    checkpoint_job(job_id, lease_token, lambda current: None)
    if connection.in_atomic_block:
        raise CMSFailure("CHECKPOINT_INTEGRITY", 409)

    def prepare(current):
        with _WindowsCleanup() as storage:
            if current.checkpoint:
                artifact, path = _cleanup_target(current)
            else:
                artifact = AdminArtifact.objects.select_for_update().get(pk=current.artifact_id)
                cleanup_eligible(artifact)
                path = _path(artifact)
            artifact_bytes(artifact)
            _, identity = storage.file(artifact, current.checkpoint.get("file_identity"))
            current.checkpoint = {"cleanup_prepared": True, "sha256": artifact.sha256, "size": artifact.size,
                "artifact_version": artifact.version, "storage_profile": digest(str(path.parent)),
                "directory_identity": storage.identity, "file_identity": identity}
            current.progress_done, current.progress_total = 0, 1

    checkpoint_job(job_id, lease_token, prepare)

    unlinked = False

    def remove(current):
        nonlocal unlinked
        with _WindowsCleanup() as storage:
            artifact, _ = _cleanup_target(current)
            if storage.identity != current.checkpoint["directory_identity"]:
                raise CMSFailure("CHECKPOINT_INTEGRITY", 409)
            handle, _ = storage.file(artifact, current.checkpoint["file_identity"])
            storage.delete(handle)
            unlinked = True
        current.result = _cleanup_receipt(current, artifact)
        current.status, current.error_code = "succeeded", ""
        job_audit(current, "job.succeeded")

    try:
        job = checkpoint_job(job_id, lease_token, remove)
    except Exception:
        if unlinked:
            # Preserve a recoverable running intent instead of failing an irreversible effect.
            with policy_lock():
                current = AdminJob.objects.select_for_update().get(pk=job_id)
                if current.status == "running" and current.lease_token == lease_token:
                    current.lease_expires_at = timezone.now()
                    current.error_code = "WORKER_INTERRUPTED"
                    current.version += 1
                    current.save(update_fields=("lease_expires_at", "error_code", "version", "updated_at"))
        raise
    return job.result


def reconcile_cleanup(job):
    """Recover an unlink receipt under the caller's policy/job lock; never delete bytes."""
    try:
        with _WindowsCleanup() as storage:
            artifact, path = _cleanup_target(job)
            if storage.identity != job.checkpoint["directory_identity"]:
                raise CMSFailure("CHECKPOINT_INTEGRITY", 409)
            try:
                path.lstat()
            except FileNotFoundError:
                return _cleanup_receipt(job, artifact)
            storage.file(artifact, job.checkpoint["file_identity"])
    except (CMSFailure, OSError):
        raise CMSFailure("CHECKPOINT_INTEGRITY", 409)
    return None


def bounded_json(raw):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_BYTES:
        raise CMSFailure("JSON_LIMIT", 400)
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result
    def constant(value):
        raise ValueError("non-finite")
    try:
        text = raw.decode("utf-8")
        document = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise CMSFailure("INVALID_JSON", 400)
    stack, nodes = [(document, 0)], 0
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if depth > MAX_DEPTH or nodes > MAX_NODES:
            raise CMSFailure("JSON_LIMIT", 400)
        if isinstance(value, dict):
            if any(len(key) > 500 or any(0xD800 <= ord(c) <= 0xDFFF for c in key) for key in value):
                raise CMSFailure("JSON_LIMIT", 400)
            # Shallow checks reuse the guard without materializing thousands of deep error paths.
            if protected_paths({unicodedata.normalize("NFKC", key): None for key in value}):
                raise CMSFailure("PROTECTED_CONTENT", 400)
            stack.extend((child, depth + 1) for child in value.values())
        elif isinstance(value, list):
            if len(value) > MAX_RECORDS:
                raise CMSFailure("JSON_LIMIT", 400)
            stack.extend((child, depth + 1) for child in value)
        elif isinstance(value, str) and (len(value) > MAX_STRING or any(0xD800 <= ord(c) <= 0xDFFF for c in value)):
            raise CMSFailure("JSON_LIMIT", 400)
        elif isinstance(value, float) and not math.isfinite(value):
            raise CMSFailure("INVALID_JSON", 400)
    if not isinstance(document, dict):
        raise CMSFailure("UNSUPPORTED_SCHEMA", 400)
    return text, document


# Narrative/manual fields are deliberately absent; these are identifiers and bibliographic metadata.
ASSESSMENT_FIELDS = {
    "source": {"title", "organization", "citation", "url", "publication_year", "source_type", "authors", "doi", "pmid"},
    "instrument": {"slug", "name_en", "name_fa", "rightsholder"},
    "version": {"instrument", "key", "label", "form_kind", "publication_year", "derived_from", "construct", "intended_use"},
    "language_form": {"version", "key", "language", "label", "form_kind", "owner"},
    "study": {"key", "version", "language_form", "source", "sample_size"},
    "finding": {"key", "study", "measurement_property", "statistic", "value_text", "units"},
    "alias": {"instrument", "version", "text", "language", "alias_type", "source"},
    "access": {"key", "version", "language_form", "material_type", "use", "owner", "source"},
    "relation": {"key", "version", "language_form", "predicate", "concept", "symptom", "disorder"},
}


def _assessment(text, document):
    from .assessment_publication import MODELS
    try:
        parse_assessment(text)
    except CommandError:
        raise CMSFailure("UNSUPPORTED_SCHEMA", 400)
    if (set(document) - {"schema_version", "dataset_metadata", "records"}
            or set(document["dataset_metadata"]) - {"key", "version", "dataset_name"}):
        raise CMSFailure("UNSUPPORTED_SCHEMA", 400)
    for row in document["records"]:
        category, data = row.get("category"), row.get("data")
        if (set(row) - {"id", "category", "data", "sources"} or type(category) is not str or category not in ASSESSMENT_FIELDS
                or not isinstance(data, dict) or set(data) - ASSESSMENT_FIELDS[category]):
            raise CMSFailure("PROTECTED_CONTENT", 400)
        for key, value in data.items():
            if value is None:
                continue
            field = MODELS[category]._meta.get_field(key)
            if key in {"publication_year", "sample_size"}:
                if type(value) is not int or not 0 < value <= (9999 if key == "publication_year" else 1000000000):
                    raise CMSFailure("INVALID_METADATA", 400)
            elif type(value) is not str or len(value) > min(field.max_length or 255, 500) or any(c in value for c in "\n\r\t"):
                raise CMSFailure("PROTECTED_CONTENT", 400)
            elif field.choices and value not in {choice for choice, _ in field.choices}:
                raise CMSFailure("INVALID_METADATA", 400)
        for link in row.get("sources", []):
            if (set(link) != {"source", "note"} or len(link["source"]) > 300 or len(link["note"]) > 200
                    or any(c in link["note"] for c in "\n\r\t")):
                raise CMSFailure("PROTECTED_CONTENT", 400)
    return [("assessment", row, index) for index, row in enumerate(document["records"])]


def prepare_document(kind, raw):
    text, document = bounded_json(raw)
    importer = ResearchImporter()
    if kind == "research_json":
        if (set(document) - {*LIST_SECTIONS, "dataset_metadata", "statistics", "quality_control", "schema_version"}
                or document.get("schema_version") not in (None, "psychology-atlas-research-v1")
                or not isinstance(document.get("dataset_metadata"), dict)
                or not any(section in document for section in LIST_SECTIONS)):
            raise CMSFailure("UNSUPPORTED_SCHEMA", 400)
        if any(not isinstance(document.get(key, {}), dict) for key in ("statistics", "quality_control")):
            raise CMSFailure("UNSUPPORTED_SCHEMA", 400)
        rows = []
        for section in LIST_SECTIONS:
            values = document.get(section, [])
            if not isinstance(values, list) or any(not isinstance(value, dict) for value in values):
                raise CMSFailure("UNSUPPORTED_SCHEMA", 400)
            if len(rows) + len(values) > MAX_RECORDS:
                raise CMSFailure("JSON_LIMIT", 400)
            rows.extend((section, value, index) for index, value in enumerate(values))
        metadata = document["dataset_metadata"]
        audit_data = importer._build_ingestion_audit(document)
    elif kind == "assessment_json":
        rows = _assessment(text, document)
        metadata = document["dataset_metadata"]
        audit_data = {"assessment_staging_schema": ASSESSMENT_SCHEMA}
    elif kind == "dsm_json":
        from .dsm_import import _collect_nodes, _validate_document, NODE_ROOT_KEYS
        if not any(key in document for key in NODE_ROOT_KEYS):
            raise CMSFailure("UNSUPPORTED_SCHEMA", 400)
        try:
            nodes = _collect_nodes(document)
            _validate_document(document, nodes)
        except (ValueError, TypeError, AttributeError):
            raise CMSFailure("UNSUPPORTED_SCHEMA", 400)
        if not nodes:
            raise CMSFailure("UNSUPPORTED_SCHEMA", 400)
        rows = [("dsm", node, index) for index, node in enumerate(nodes)]
        metadata = {key: value for key, value in document.items() if key not in NODE_ROOT_KEYS}
        audit_data = {"dsm_staging_schema": "dsm-master"}
    elif kind == "evidence_json":
        if (len(raw) > MAX_EVIDENCE_BYTES or set(document) != {"schema_version", "title", "source_url", "locator"}
                or document["schema_version"] != "psychology-atlas-evidence-v1"
                or any(type(document[key]) is not str or not 0 < len(document[key]) <= limit
                    for key, limit in (("title", 500), ("source_url", 2000), ("locator", 1000)))
                or not re.fullmatch(r"https?://[^\s]+", document["source_url"])):
            raise CMSFailure("UNSUPPORTED_SCHEMA", 400)
        return text, document, {}, [], {}
    else:
        raise CMSFailure("UNSUPPORTED_SCHEMA", 400)
    if len(rows) > MAX_RECORDS:
        raise CMSFailure("JSON_LIMIT", 400)
    identities = set()
    for section, value, index in rows:
        identity = (section, _record_identity(importer, section, value, index))
        if identity in identities or len(identity[1]) > 300:
            raise CMSFailure("DUPLICATE_RECORD", 400)
        identities.add(identity)
    return text, document, metadata, rows, {**audit_data, "list_record_total": len(rows), "cms_domain": KINDS[kind]}


def validate_artifact(actor_id, session_id, artifact_id, expected, request_id):
    with policy_lock():
        actor = _write_authority(actor_id, session_id)
        artifact = get_artifact(actor, artifact_id, lock=True)
        _edit_scope(actor, artifact)
        if type(expected) is not int or artifact.version != expected:
            raise CMSFailure("STALE_REVISION", 412)
        if artifact.state != "quarantine" or artifact.expires_at <= timezone.now():
            raise CMSFailure("ARTIFACT_NOT_READY", 409)
    code = ""
    try:
        prepare_document(artifact.kind, artifact_bytes(artifact))
    except CMSFailure as error:
        code = str(error.detail["code"])
    with policy_lock() as policy:
        actor = _write_authority(actor_id, session_id)
        current = get_artifact(actor, artifact_id, lock=True)
        _edit_scope(actor, current)
        if type(expected) is not int or current.version != expected:
            raise CMSFailure("STALE_REVISION", 412)
        if current.state != "quarantine" or current.expires_at <= timezone.now():
            raise CMSFailure("ARTIFACT_NOT_READY", 409)
        current.state, current.validation_code = ("rejected", code) if code else ("ready", "JSON_VALID")
        current.version += 1
        current.save(update_fields=("state", "validation_code", "version"))
        audit(actor, "artifact.validate", "ARTIFACT_VALIDATE", request_id, artifact=current, policy=policy)
        return current


def revoke_artifact(actor_id, session_id, artifact_id, expected, request_id):
    with policy_lock() as policy:
        actor = _write_authority(actor_id, session_id)
        artifact = get_artifact(actor, artifact_id, lock=True)
        _edit_scope(actor, artifact)
        if type(expected) is not int or artifact.version != expected:
            raise CMSFailure("STALE_REVISION", 412)
        if artifact.state == "revoked":
            raise CMSFailure("ARTIFACT_NOT_READY", 409)
        artifact.state = "revoked"
        artifact.version += 1
        artifact.save(update_fields=("state", "version"))
        audit(actor, "artifact.revoke", "ARTIFACT_REVOKE", request_id, artifact=artifact, policy=policy)
        return artifact


def _record_identity(importer, section, row, index):
    if section == "assessment":
        return row["id"]
    if section == "dsm":
        return row.master_id
    return importer._external_id(section, row, index)


def _record_fields(importer, section, row, index):
    if section == "assessment":
        result = archive_fields(row)
    elif section == "dsm":
        from .dsm_import import _as_text, _prune_nested_nodes
        result = {"section": "dsm_record", "external_id": row.master_id, "canonical_key": "dsm:" + row.master_id,
            "name_en": _as_text(row.profile.get("نام_انگلیسی"))[:500],
            "name_fa": _as_text(row.profile.get("نام_فارسی"))[:500], "payload": _prune_nested_nodes(row.source),
            "source_ids": row.profile.get("منابع_پایه") or []}
    else:
        external_id = importer._external_id(section, row, index)
        name_en, name_fa = importer._names(section, row)
        result = {"section": section, "external_id": external_id, "payload": row,
            "canonical_key": importer._canonical_key(section, row, external_id)[:400],
            "slug": importer._safe_slug(row.get("slug"))[:220], "name_en": name_en[:500], "name_fa": name_fa[:500],
            "source_ids": importer._source_ids(row)}
    return {**result, "review_status": "unreviewed", "verification_status": "staging_only"}


def process_intake(job_id, lease_token):
    from .cms_jobs import checkpoint_job
    job = checkpoint_job(job_id, lease_token, lambda current: None)
    completed = reconcile_intake(job)
    if completed is not None:
        return completed
    artifact = AdminArtifact.objects.get(pk=job.artifact_id)
    raw = artifact_bytes(artifact)
    text, document, metadata, rows, audit_data = prepare_document(artifact.kind, raw)
    existing = ResearchDataset.objects.defer("raw_text", "raw_document").filter(source_sha256=artifact.sha256).first()
    if existing is not None:
        with policy_lock():
            get_dataset(job.actor, existing.pk)
        if existing.raw_text != text or existing.raw_document != document:
            raise CMSFailure("ARCHIVE_INTEGRITY", 409)
    importer = ResearchImporter()
    name = str(metadata.get("dataset_name") or metadata.get("key") or Path(artifact.filename).stem)[:300]
    version = str(metadata.get("dataset_version") or metadata.get("version") or "")[:120]
    # Full SHA keeps unrelated identities distinct even when human labels are equal.
    key = (slugify(name + "-" + version) or "research")[:110] + "-" + artifact.sha256
    defaults = {"key": key, "source_filename": artifact.filename, "dataset_name": name, "dataset_version": version,
        "generated_at_text": str(metadata.get("generated_at") or metadata.get("generated") or "")[:120],
        "metadata": metadata, "statistics": document.get("statistics", {}), "quality_control": document.get("quality_control", {}),
        "raw_document": document, "raw_text": text, "is_active": False,
        "ingestion_audit": {**audit_data, "cms_intake_job": str(job.pk), "cms_owner_ref": job.actor_ref}}

    def envelope(current):
        if current.checkpoint:
            checkpoint = current.checkpoint
            if (checkpoint.get("sha256") != artifact.sha256 or type(checkpoint.get("offset")) is not int
                    or not 0 <= checkpoint["offset"] <= len(rows) or type(checkpoint.get("dataset_id")) is not int):
                raise CMSFailure("CHECKPOINT_INTEGRITY", 409)
            dataset = ResearchDataset.objects.only("id", "source_sha256", "ingestion_audit").select_for_update().filter(
                pk=checkpoint["dataset_id"], source_sha256=artifact.sha256).first()
            if dataset is None:
                raise CMSFailure("CHECKPOINT_INTEGRITY", 409)
            if checkpoint.get("duplicate") is not True and dataset.ingestion_audit.get("cms_intake_job") != str(current.pk):
                raise CMSFailure("CHECKPOINT_INTEGRITY", 409)
            expected_count = len(rows) if checkpoint.get("duplicate") else checkpoint["offset"]
            if dataset.records.count() != expected_count:
                raise CMSFailure("ARCHIVE_INTEGRITY", 409)
        else:
            dataset, created = ResearchDataset.objects.only("id", "source_sha256", "ingestion_audit").get_or_create(
                source_sha256=artifact.sha256, defaults=defaults)
            own = dataset.ingestion_audit.get("cms_intake_job") == str(current.pk)
            if not created:
                get_dataset(current.actor, dataset.pk, lock=True)
                if not own:
                    origin_id = dataset.ingestion_audit.get("cms_intake_job")
                    if origin_id:
                        origin = AdminJob.objects.select_for_update().filter(pk=_uuid(origin_id)).first()
                        if (origin is None or origin.status != "succeeded"
                                or origin.checkpoint.get("dataset_id") != dataset.pk
                                or origin.checkpoint.get("sha256") != artifact.sha256
                                or origin.checkpoint.get("offset") != len(rows)):
                            raise CMSFailure("INTAKE_INCOMPLETE", 409)
                    if dataset.records.count() != len(rows):
                        raise CMSFailure("ARCHIVE_INTEGRITY", 409)
            current.checkpoint = {"dataset_id": dataset.pk, "sha256": artifact.sha256,
                "offset": 0, "duplicate": not created and not own, "complete": not rows,
                "verified_duplicate": not rows and not created and not own}
            audit(current.actor, "research.intake", "RESEARCH_INTAKE", uuid.uuid4(), record=dataset)
        current.progress_total = len(rows)
        current.progress_done = current.checkpoint["offset"]

    job = checkpoint_job(job_id, lease_token, envelope)
    while job.checkpoint["offset"] < len(rows):
        start = job.checkpoint["offset"]
        end = min(start + 100, len(rows))
        prepared = [_record_fields(importer, section, value, index) for section, value, index in rows[start:end]]

        def chunk(current):
            if current.checkpoint != job.checkpoint:
                raise CMSFailure("CHECKPOINT_INTEGRITY", 409)
            dataset = ResearchDataset.objects.only("id", "source_sha256", "ingestion_audit").select_for_update().get(
                pk=current.checkpoint["dataset_id"])
            if (dataset.source_sha256 != artifact.sha256 or not current.checkpoint["duplicate"]
                    and dataset.ingestion_audit.get("cms_intake_job") != str(current.pk)):
                raise CMSFailure("CHECKPOINT_INTEGRITY", 409)
            for fields in prepared:
                identity = {key: fields[key] for key in ("section", "external_id")}
                if current.checkpoint["duplicate"]:
                    record = ResearchRecord.objects.filter(dataset=dataset, **identity).first()
                    valid = record is not None and record.payload == fields["payload"]
                else:
                    record, created = ResearchRecord.objects.get_or_create(dataset=dataset, **identity,
                        defaults={key: value for key, value in fields.items() if key not in identity})
                    valid = created or all(getattr(record, key) == value for key, value in fields.items())
                if not valid:
                    raise CMSFailure("ARCHIVE_INTEGRITY", 409)
            current.checkpoint = {**current.checkpoint, "offset": end, "complete": end == len(rows),
                "verified_duplicate": current.checkpoint["duplicate"] and end == len(rows)}
            current.progress_done = end

        job = checkpoint_job(job_id, lease_token, chunk)
    result = reconcile_intake(job)
    if result is None:
        raise CMSFailure("CHECKPOINT_INTEGRITY", 409)
    return result


def reconcile_intake(job):
    """Read a committed completion receipt, including after the final attempt crashed."""
    checkpoint = job.checkpoint
    if not isinstance(checkpoint, dict):
        raise CMSFailure("CHECKPOINT_INTEGRITY", 409)
    if "complete" in checkpoint and type(checkpoint["complete"]) is not bool:
        raise CMSFailure("CHECKPOINT_INTEGRITY", 409)
    if checkpoint.get("complete") is not True:
        return None
    total, offset, dataset_id = job.progress_total, checkpoint.get("offset"), checkpoint.get("dataset_id")
    if (type(total) is not int or not 0 <= total <= MAX_RECORDS or type(offset) is not int
            or offset != total or type(job.progress_done) is not int or job.progress_done != total
            or type(dataset_id) is not int or dataset_id <= 0 or type(checkpoint.get("duplicate")) is not bool):
        raise CMSFailure("CHECKPOINT_INTEGRITY", 409)
    artifact = AdminArtifact.objects.filter(pk=job.artifact_id).first()
    dataset = ResearchDataset.objects.defer("raw_text", "raw_document").filter(pk=dataset_id).first()
    if (artifact is None or artifact.kind not in KINDS or dataset is None
            or not re.fullmatch(r"[0-9a-f]{64}", artifact.sha256)
            or not isinstance(dataset.ingestion_audit, dict)
            or checkpoint.get("sha256") != artifact.sha256 or dataset.source_sha256 != artifact.sha256
            or dataset.ingestion_audit.get("list_record_total") != total or dataset.records.count() != total):
        raise CMSFailure("CHECKPOINT_INTEGRITY", 409)
    if checkpoint["duplicate"]:
        if checkpoint.get("verified_duplicate") is not True:
            raise CMSFailure("CHECKPOINT_INTEGRITY", 409)
    elif (dataset.ingestion_audit.get("cms_intake_job") != str(job.pk)
            or dataset.ingestion_audit.get("cms_owner_ref") != job.actor_ref):
        raise CMSFailure("CHECKPOINT_INTEGRITY", 409)
    return {"dataset_id": dataset_id, "records": total, "duplicate": checkpoint["duplicate"], "artifact_id": str(artifact.pk)}


def scoped_datasets(actor):
    require(actor, "cms_research_view")
    held = effective_permissions(actor)
    domains, sections = ["research"], list(LIST_SECTIONS)
    if "cms_dsm_view" in held:
        domains.append("dsm")
        sections.append("dsm_record")
    if "cms_assessment_view" in held:
        domains.append("assessment")
        sections.extend("assessment_" + category for category in ASSESSMENT_FIELDS)
    excluded = ResearchRecord.objects.exclude(section__in=sections).values("dataset_id")
    rows = ResearchDataset.objects.exclude(pk__in=excluded).filter(
        ~Q(ingestion_audit__has_key="cms_domain") | Q(ingestion_audit__cms_domain__in=domains))
    if "cms_owner" not in held:
        rows = rows.filter(~Q(ingestion_audit__has_key="cms_owner_ref") | Q(ingestion_audit__cms_owner_ref=attribution(actor.pk)))
    if "assessment" not in domains:
        rows = rows.exclude(ingestion_audit__has_key="assessment_staging_schema")
    if "dsm" not in domains:
        rows = rows.exclude(ingestion_audit__has_key="dsm_staging_schema")
    return rows.defer("raw_text", "raw_document", "metadata", "statistics", "quality_control").order_by("pk")


def get_dataset(actor, dataset_id, lock=False):
    rows = scoped_datasets(actor)
    if lock:
        rows = rows.select_for_update()
    dataset = rows.filter(pk=dataset_id).first()
    if dataset is None:
        raise CMSFailure("NOT_FOUND", 404)
    return dataset


def dataset_data(dataset):
    count = dataset.records.count()
    return {"id": dataset.pk, "dataset_name": dataset.dataset_name, "dataset_version": dataset.dataset_version,
        "sha256": dataset.source_sha256, "source_filename": dataset.source_filename,
        "records": count, "created_at": dataset.created_at,
        "intake_complete": count == dataset.ingestion_audit.get("list_record_total", count)}


def get_record(actor, record_id, lock=False):
    rows = ResearchRecord.objects.filter(dataset_id__in=scoped_datasets(actor).values("pk"))
    if lock:
        rows = rows.select_for_update()
    record = rows.filter(pk=record_id).first()
    if record is None:
        raise CMSFailure("NOT_FOUND", 404)
    return record


def decision_data(decision, actor):
    if decision.mapping.get("source_ids") and "cms_source_view" not in effective_permissions(actor):
        raise CMSFailure("NOT_FOUND", 404)
    return {"id": decision.pk, "sequence": decision.sequence, "action": decision.action,
        "mapping": decision.mapping, "reason": decision.reason, "actor_ref": decision.actor_ref,
        "created_at": decision.created_at}


def record_data(record, actor):
    latest = record.cms_decisions.order_by("-sequence").first()
    return {"id": record.pk, "dataset_id": record.dataset_id, "section": record.section,
        "external_id": record.external_id, "name_en": record.name_en, "name_fa": record.name_fa,
        "version": latest.sequence if latest else 0, "decision": decision_data(latest, actor) if latest else None,
        "staging_state": latest.action if latest else "unmapped"}


def _mapping(actor, record, value):
    from .cms_governance import source_snapshot
    if not isinstance(value, dict) or set(value) - {"canonical_key", "name_en", "name_fa", "source_ids"}:
        raise CMSFailure("INVALID_MAPPING", 400)
    result = {}
    for key, limit in (("canonical_key", 400), ("name_en", 500), ("name_fa", 500)):
        text = value.get(key, getattr(record, key))
        if type(text) is not str or len(text) > limit or any(unicodedata.category(c).startswith("C") and c != "\u200c" for c in text):
            raise CMSFailure("INVALID_MAPPING", 400)
        result[key] = text.strip()
    if not result["canonical_key"] or not (result["name_en"] or result["name_fa"]):
        raise CMSFailure("INVALID_MAPPING", 400)
    sources = value.get("source_ids", [])
    if sources:
        require(actor, "cms_source_view")
    source_state = source_snapshot(sources, lock=True)
    if source_state["missing_source_ids"] or source_state["unavailable_source_ids"]:
        raise CMSFailure("INVALID_MAPPING", 400)
    return {**result, "source_ids": sorted(set(sources))}


def decide_record(actor_id, session_id, record_id, expected, action, mapping, reason, request_id):
    capabilities = {"map": "cms_research_map", "reject": "cms_research_reject", "defer": "cms_research_defer", "stage": "cms_research_derive"}
    if type(action) is not str or action not in capabilities or reason != "RESEARCH_" + action.upper():
        raise CMSFailure("INVALID_DECISION", 400)
    with policy_lock() as policy:
        actor = User.objects.get(pk=actor_id)
        current_session(session_id, actor)
        require(actor, capabilities[action])
        record = get_record(actor, record_id, lock=True)
        latest = record.cms_decisions.order_by("-sequence").first()
        sequence = latest.sequence if latest else 0
        if type(expected) is not int or sequence != expected:
            raise CMSFailure("STALE_REVISION", 412)
        if action == "map":
            mapping = _mapping(actor, record, mapping)
        elif action == "stage":
            if latest is None or latest.action != "map" or mapping not in ({}, latest.mapping):
                raise CMSFailure("MAPPING_REQUIRED", 409)
            if latest.payload_digest != digest(record.payload):
                raise CMSFailure("ARCHIVE_INTEGRITY", 409)
            dataset = record.dataset
            if dataset.records.count() != dataset.ingestion_audit.get("list_record_total", dataset.records.count()):
                raise CMSFailure("INTAKE_INCOMPLETE", 409)
            mapping = _mapping(actor, record, latest.mapping)
        elif mapping != {}:
            raise CMSFailure("INVALID_MAPPING", 400)
        decision = ResearchRecordDecision.objects.create(record=record, sequence=sequence + 1,
            action=action, mapping=mapping, reason=reason, actor=actor, actor_ref=attribution(actor_id),
            payload_digest=digest(record.payload))
        audit(actor, "research.decision", reason, request_id, record=record, policy=policy)
        return decision


def raw_preview(actor_id, session_id, record_id, purpose, reason, request_id):
    if type(purpose) is not str or purpose not in PURPOSES or reason != "RESEARCH_RAW":
        raise CMSFailure("INVALID_PURPOSE", 400)
    with policy_lock() as policy:
        actor = User.objects.get(pk=actor_id)
        current_session(session_id, actor)
        require(actor, "cms_research_raw_read")
        record = get_record(actor, record_id, lock=True)
        # Old CLI archives may predate the private upload validator.
        bounded_json(json.dumps(record.payload, ensure_ascii=False).encode("utf-8"))
        if record.section.startswith("assessment_"):
            _assessment(json.dumps({"schema_version": ASSESSMENT_SCHEMA,
                "dataset_metadata": {"key": "preview", "version": "1"}, "records": [record.payload]}),
                {"schema_version": ASSESSMENT_SCHEMA, "dataset_metadata": {"key": "preview", "version": "1"}, "records": [record.payload]})
        audit(actor, "research.raw", reason, request_id, record=record, policy=policy)
        return {"id": record.pk, "dataset_id": record.dataset_id, "section": record.section, "payload": record.payload}
