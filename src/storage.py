"""
StudioMap — Storage Layer
==========================
All file I/O goes through this module.
The app never reads or writes files directly.

Two backends:
  local  — JSON files on disk (default)
  drive  — Google Drive via Service Account

Switching backends is one config change.
Local files always exist as a cache regardless of mode.

Install for Drive: pip install google-api-python-client google-auth
"""

import io
import json
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
# LOCAL — STUDIOS
# ══════════════════════════════════════════════════════════════════════════════

def list_studios() -> list[Path]:
    return sorted(STUDIOS_DIR.glob("*.json"))


def load_studio(path: Path) -> StudioProfile:
    data = json.loads(path.read_text(encoding="utf-8"))
    return StudioProfile(**data)


def save_studio(profile: StudioProfile, path: Path = None) -> Path:
    if path is None:
        path = STUDIOS_DIR / profile.filename()
    path.write_text(
        json.dumps(profile.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    if _is_drive():
        _drive_write_json("studios", path.name, profile.model_dump())
    return path


def delete_studio(path: Path):
    path.unlink(missing_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
# LOCAL — PLANS
# ══════════════════════════════════════════════════════════════════════════════

def list_plans() -> list[Path]:
    return sorted(PLANS_DIR.glob("*.json"), reverse=True)


def load_plan(path: Path) -> LessonPlan:
    data = json.loads(path.read_text(encoding="utf-8"))
    return LessonPlan(**data)


def save_plan(plan: LessonPlan) -> Path:
    path = PLANS_DIR / plan.filename()
    path.write_text(
        json.dumps(plan.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    return path


def delete_plan(path: Path):
    path.unlink(missing_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
# IMAGES
# ══════════════════════════════════════════════════════════════════════════════

def save_image(file_bytes: bytes, filename: str) -> str:
    """Save image bytes. Returns relative path string."""
    dest = IMAGES_DIR / filename
    dest.write_bytes(file_bytes)
    return str(dest.relative_to(DATA_DIR.parent))


def image_path(rel: str) -> Path:
    """Resolve a relative image path to absolute."""
    return DATA_DIR.parent / rel


# ══════════════════════════════════════════════════════════════════════════════
# BACKUP
# ══════════════════════════════════════════════════════════════════════════════

def create_backup_zip() -> tuple[bytes, str]:
    """Zip all data. Returns (bytes, filename)."""
    buf = io.BytesIO()
    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"studiomap_backup_{ts}.zip"

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for folder in ["studios", "plans", "images"]:
            d = DATA_DIR / folder
            if not d.exists():
                continue
            for f in d.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(DATA_DIR.parent))
        cfg_file = DATA_DIR / "config.json"
        if cfg_file.exists():
            zf.write(cfg_file, cfg_file.relative_to(DATA_DIR.parent))

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
        for path in list(list_studios()) + list(list_plans()):
            data = json.loads(path.read_text())
            folder = "studios" if path.parent == STUDIOS_DIR else "plans"
            _drive_write_json(folder, path.name, data)
            count += 1
        return True, f"Synced {count} files to Drive.", count
    except Exception as e:
        return False, f"Sync failed: {e}", 0


# ══════════════════════════════════════════════════════════════════════════════
# GOOGLE DRIVE — INTERNAL
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
    # Check if file exists to update rather than duplicate
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
