"""
StudioMap — Storage Layer
==========================
All file I/O goes through this module.
The app never reads or writes files directly.

Three backends, switched via STORAGE_MODE env var or config:
  local  — JSON files on disk (default, dev)
  gcs    — Google Cloud Storage (Cloud Run / production)
  drive  — Google Drive via Service Account (legacy backup)

GCS mode requires:
  GCS_BUCKET env var            — bucket name
  GCS_CREDENTIALS_JSON env var  — service-account key JSON string (optional;
                                   defaults to Application Default Credentials /
                                   Workload Identity on Cloud Run)
"""

import io
import json
import os
import zipfile
from pathlib import Path
from typing import Optional
from datetime import datetime

from config import (
    STUDIOS_DIR, PLANS_DIR, IMAGES_DIR, DATA_DIR,
    CREDS_FILE, load_config, save_config, now_str
)
from models import StudioProfile, LessonPlan


# ══════════════════════════════════════════════════════════════════════════════
# STORAGE BACKEND ABSTRACTION
# ══════════════════════════════════════════════════════════════════════════════

class _Backend:
    """
    Minimal key/value storage interface.
    Keys are slash-separated paths like "studios/foo.json" or "images/pic.jpg".
    """
    def list_keys(self, prefix: str) -> list[str]:
        """Return sorted filenames (not full keys) under the given prefix."""
        raise NotImplementedError

    def read(self, key: str) -> bytes:
        raise NotImplementedError

    def write(self, key: str, data: bytes) -> None:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError

    def exists(self, key: str) -> bool:
        raise NotImplementedError


class _LocalBackend(_Backend):
    """Reads and writes plain files under DATA_DIR."""

    def __init__(self, base: Path):
        self._base = base

    def list_keys(self, prefix: str) -> list[str]:
        d = self._base / prefix
        if not d.exists():
            return []
        return sorted(p.name for p in d.iterdir() if p.is_file())

    def read(self, key: str) -> bytes:
        return (self._base / key).read_bytes()

    def write(self, key: str, data: bytes) -> None:
        path = self._base / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def delete(self, key: str) -> None:
        (self._base / key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return (self._base / key).exists()


class _GCSBackend(_Backend):
    """
    Reads and writes to a Google Cloud Storage bucket.

    Authentication (in priority order):
      1. GCS_CREDENTIALS_JSON env var — service-account key as a JSON string
      2. Application Default Credentials — automatically used on Cloud Run via
         Workload Identity; locally via `gcloud auth application-default login`
    """

    def __init__(self, bucket_name: str, credentials_json: Optional[str] = None):
        try:
            from google.cloud import storage as gcs_lib
        except ImportError:
            raise ImportError(
                "google-cloud-storage is required for GCS mode.\n"
                "Run:  pip install google-cloud-storage"
            )

        if credentials_json:
            from google.oauth2.service_account import Credentials
            info = json.loads(credentials_json)
            creds = Credentials.from_service_account_info(
                info,
                scopes=["https://www.googleapis.com/auth/devstorage.read_write"]
            )
            self._client = gcs_lib.Client(credentials=creds, project=info.get("project_id"))
        else:
            # Workload Identity on Cloud Run, or ADC locally
            self._client = gcs_lib.Client()

        self._bucket_name = bucket_name
        self._bucket = self._client.bucket(bucket_name)

    def list_keys(self, prefix: str) -> list[str]:
        full_prefix = prefix.rstrip("/") + "/"
        blobs = self._client.list_blobs(self._bucket_name, prefix=full_prefix)
        names = []
        for b in blobs:
            name = b.name[len(full_prefix):]
            if name and "/" not in name:   # skip sub-"directories"
                names.append(name)
        return sorted(names)

    def read(self, key: str) -> bytes:
        return self._bucket.blob(key).download_as_bytes()

    def write(self, key: str, data: bytes) -> None:
        content_type = "application/json" if key.endswith(".json") else "application/octet-stream"
        self._bucket.blob(key).upload_from_string(data, content_type=content_type)

    def delete(self, key: str) -> None:
        blob = self._bucket.blob(key)
        try:
            blob.delete()
        except Exception:
            pass   # already gone

    def exists(self, key: str) -> bool:
        return self._bucket.blob(key).exists()


# ── Backend singleton (one per process) ──────────────────────────────────────

_backend_instance: Optional[_Backend] = None


def _get_backend() -> _Backend:
    """
    Return the active storage backend.
    Storage mode is resolved (in order) from:
      1. STORAGE_MODE environment variable
      2. storage_mode in config.json
    """
    global _backend_instance
    if _backend_instance is not None:
        return _backend_instance

    mode = os.environ.get("STORAGE_MODE") or load_config().get("storage_mode", "local")

    if mode == "gcs":
        bucket = os.environ.get("GCS_BUCKET") or load_config().get("gcs_bucket", "")
        if not bucket:
            raise ValueError(
                "GCS storage mode requires a bucket name. "
                "Set the GCS_BUCKET environment variable or gcs_bucket in config."
            )
        creds = os.environ.get("GCS_CREDENTIALS_JSON")
        _backend_instance = _GCSBackend(bucket, creds)
    else:
        _backend_instance = _LocalBackend(DATA_DIR)

    return _backend_instance


def reset_backend():
    """
    Clear the cached backend instance.
    Call this after changing storage_mode in Settings so the next
    operation picks up the new configuration.
    """
    global _backend_instance
    _backend_instance = None


# ══════════════════════════════════════════════════════════════════════════════
# STUDIOS
# ══════════════════════════════════════════════════════════════════════════════

def list_studios() -> list[Path]:
    names = _get_backend().list_keys("studios")
    return [STUDIOS_DIR / n for n in names if n.endswith(".json")]


def load_studio(path: Path) -> StudioProfile:
    raw = _get_backend().read(f"studios/{path.name}")
    return StudioProfile(**json.loads(raw))


def save_studio(profile: StudioProfile, path: Path = None) -> Path:
    if path is None:
        path = STUDIOS_DIR / profile.filename()
    data = json.dumps(profile.model_dump(), indent=2, ensure_ascii=False).encode()
    _get_backend().write(f"studios/{path.name}", data)
    if _is_drive():
        _drive_write_json("studios", path.name, profile.model_dump())
    return path


def delete_studio(path: Path):
    _get_backend().delete(f"studios/{path.name}")
    if _is_drive():
        pass   # Drive deletion not implemented; files remain as archive


# ══════════════════════════════════════════════════════════════════════════════
# PLANS
# ══════════════════════════════════════════════════════════════════════════════

def list_plans() -> list[Path]:
    names = _get_backend().list_keys("plans")
    return [PLANS_DIR / n for n in reversed(sorted(names)) if n.endswith(".json")]


def load_plan(path: Path) -> LessonPlan:
    raw = _get_backend().read(f"plans/{path.name}")
    return LessonPlan(**json.loads(raw))


def save_plan(plan: LessonPlan) -> Path:
    path = PLANS_DIR / plan.filename()
    data = json.dumps(plan.model_dump(), indent=2, ensure_ascii=False).encode()
    _get_backend().write(f"plans/{path.name}", data)
    return path


def delete_plan(path: Path):
    _get_backend().delete(f"plans/{path.name}")


# ══════════════════════════════════════════════════════════════════════════════
# IMAGES
# ══════════════════════════════════════════════════════════════════════════════

def save_image(file_bytes: bytes, filename: str) -> str:
    """
    Save image bytes. Returns a relative path string.
    In GCS mode the image is also cached locally for immediate display.
    """
    _get_backend().write(f"images/{filename}", file_bytes)
    # Always keep a local copy so Streamlit can serve it directly
    local = IMAGES_DIR / filename
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_bytes(file_bytes)
    return str(local.relative_to(DATA_DIR.parent))


def image_path(rel: str) -> Path:
    """
    Resolve a relative image path to an absolute local path.
    In GCS mode, downloads from GCS to the local cache on first access.
    """
    local = DATA_DIR.parent / rel
    if not local.exists():
        # Cache miss — try downloading from GCS
        try:
            b = _get_backend()
            filename = Path(rel).name
            data = b.read(f"images/{filename}")
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(data)
        except Exception:
            pass   # image unavailable; caller handles missing file
    return local


# ══════════════════════════════════════════════════════════════════════════════
# CONFIG PERSISTENCE (GCS mode)
# ══════════════════════════════════════════════════════════════════════════════

def load_remote_config() -> dict:
    """
    In GCS mode, read config.json from the bucket.
    Falls back to an empty dict on any error (first boot, missing file, etc.).
    """
    try:
        raw = _get_backend().read("config.json")
        return json.loads(raw)
    except Exception:
        return {}


def save_remote_config(cfg: dict):
    """In GCS mode, persist config.json to the bucket."""
    _get_backend().write("config.json", json.dumps(cfg, indent=2).encode())


# ══════════════════════════════════════════════════════════════════════════════
# BACKUP
# ══════════════════════════════════════════════════════════════════════════════

def create_backup_zip() -> tuple[bytes, str]:
    """Zip all data. Returns (bytes, filename)."""
    buf = io.BytesIO()
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"studiomap_backup_{ts}.zip"

    b = _get_backend()

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for folder in ("studios", "plans", "images"):
            for fname in b.list_keys(folder):
                key = f"{folder}/{fname}"
                try:
                    zf.writestr(f"data/{key}", b.read(key))
                except Exception:
                    pass
        # Include config
        try:
            zf.writestr("data/config.json", b.read("config.json"))
        except Exception:
            pass

    buf.seek(0)
    return buf.read(), name


def backup_to_drive() -> tuple[bool, str]:
    """Upload a backup ZIP to Google Drive."""
    try:
        from googleapiclient.http import MediaIoBaseUpload
        cfg = load_config()
        folder_id = cfg.get("drive_backup_folder_id") or cfg.get("drive_folder_id")
        if not folder_id:
            return False, "No Drive folder configured in Settings."

        svc = _drive_service()
        zip_bytes, zip_name = create_backup_zip()
        media = MediaIoBaseUpload(io.BytesIO(zip_bytes), mimetype="application/zip")
        svc.files().create(
            body={"name": zip_name, "parents": [folder_id]},
            media_body=media, fields="id"
        ).execute()

        cfg["last_backup_drive"] = now_str()
        save_config(cfg)
        return True, f"Backup uploaded: {zip_name}"
    except Exception as e:
        return False, f"Drive backup failed: {e}"


def sync_to_drive() -> tuple[bool, str, int]:
    """Push all local studios and plans to Drive."""
    try:
        count = 0
        b = _get_backend()
        for folder in ("studios", "plans"):
            for fname in b.list_keys(folder):
                data = json.loads(b.read(f"{folder}/{fname}"))
                _drive_write_json(folder, fname, data)
                count += 1
        return True, f"Synced {count} files to Drive.", count
    except Exception as e:
        return False, f"Sync failed: {e}", 0


# ══════════════════════════════════════════════════════════════════════════════
# GOOGLE DRIVE — INTERNAL (legacy backup/sync, unchanged)
# ══════════════════════════════════════════════════════════════════════════════

def _is_drive() -> bool:
    return load_config().get("storage_mode") == "drive"


def _drive_service():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    if not CREDS_FILE.exists():
        raise FileNotFoundError(
            f"credentials.json not found at {CREDS_FILE}. "
            "Download from Google Cloud Console → Service Accounts → Keys."
        )
    creds = service_account.Credentials.from_service_account_file(
        str(CREDS_FILE),
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build("drive", "v3", credentials=creds)


def _drive_get_folder(svc, parent_id: str, name: str) -> str:
    q = (f"'{parent_id}' in parents and name='{name}' and "
         f"mimeType='application/vnd.google-apps.folder' and trashed=false")
    files = svc.files().list(q=q, fields="files(id)").execute().get("files", [])
    if files:
        return files[0]["id"]
    meta = {"name": name, "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id]}
    return svc.files().create(body=meta, fields="id").execute()["id"]


def _drive_write_json(folder: str, filename: str, data: dict):
    from googleapiclient.http import MediaIoBaseUpload
    cfg  = load_config()
    svc  = _drive_service()
    fid  = _drive_get_folder(svc, cfg["drive_folder_id"], folder)
    content = json.dumps(data, indent=2, ensure_ascii=False).encode()
    media = MediaIoBaseUpload(io.BytesIO(content), mimetype="application/json")
    q = f"'{fid}' in parents and name='{filename}' and trashed=false"
    existing = svc.files().list(q=q, fields="files(id)").execute().get("files", [])
    if existing:
        svc.files().update(fileId=existing[0]["id"], media_body=media).execute()
    else:
        svc.files().create(
            body={"name": filename, "parents": [fid]},
            media_body=media, fields="id"
        ).execute()


def test_drive() -> tuple[bool, str]:
    try:
        cfg = load_config()
        if not cfg.get("drive_folder_id"):
            return False, "Drive folder ID not set in Settings."
        svc = _drive_service()
        r = svc.files().get(fileId=cfg["drive_folder_id"], fields="name").execute()
        return True, f"Connected → folder: {r.get('name')}"
    except Exception as e:
        return False, str(e)


def test_gcs() -> tuple[bool, str]:
    """Test GCS connection and bucket access."""
    try:
        b = _get_backend()
        if not isinstance(b, _GCSBackend):
            return False, "Storage mode is not set to GCS."
        # Try listing to confirm bucket access
        b.list_keys("studios")
        return True, f"Connected to GCS bucket: {b._bucket_name}"
    except Exception as e:
        return False, f"GCS error: {e}"
