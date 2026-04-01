"""
StudioMap — Configuration
==========================
Single source of truth for all paths, constants, and settings.
Nothing is hardcoded anywhere else — everything comes from here.
"""

import os
from pathlib import Path
import json
from datetime import datetime

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent.parent
DATA_DIR     = BASE_DIR / "data"
STUDIOS_DIR  = DATA_DIR / "studios"
PLANS_DIR    = DATA_DIR / "plans"
UPLOADS_DIR  = DATA_DIR / "uploads"
IMAGES_DIR   = DATA_DIR / "images"
ACTIVITY_DIR = DATA_DIR / "activity"
CONFIG_FILE  = DATA_DIR / "config.json"
CREDS_FILE   = BASE_DIR / "credentials.json"   # Google Drive service account key

# Create all directories on import
for _d in [STUDIOS_DIR, PLANS_DIR, UPLOADS_DIR, IMAGES_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# ── AI ────────────────────────────────────────────────────────────────────────
CLAUDE_MODEL    = "claude-sonnet-4-20250514"
OPENAI_MODEL    = "gpt-4o"
MAX_TOKENS      = 4096
PDF_MAX_TOKENS  = 8192   # for PDF → profile extraction (higher for multi-studio PDFs)

# ── Domain constants ──────────────────────────────────────────────────────────
ALL_GRADES = [str(g) for g in range(1, 13)]

ALL_SUBJECTS = [
    "English", "Mathematics", "Science", "Social Studies",
    "Hindi", "Kannada", "EVS", "Physics", "Chemistry",
    "Biology", "History", "Geography", "Computer Science",
    "Art", "Physical Education", "Other"
]

ALL_BOARDS = ["CBSE", "Karnataka State Board", "Both"]

ACTIVITY_TYPES = [
    "Individual Practice", "Pair Work", "Group Work",
    "Rotation / Stations", "Teacher-Led", "Student Presentation",
    "Project-Based", "Assessment / Quiz"
]

# ── App config defaults ───────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    "school_name":            "",
    "storage_mode":           "local",      # "local" | "drive"
    "drive_folder_id":        "",
    "drive_backup_folder_id": "",
    "ai_provider":            "anthropic",  # "anthropic" | "openai" | "local"
    "anthropic_api_key":      "",           # optional — falls back to env var
    "openai_api_key":         "",           # optional — falls back to env var
    "local_model_url":        "http://127.0.0.1:11434/v1",
    "local_model_name":       "llama3",
    "gcs_bucket":             "",           # GCS bucket name (or set GCS_BUCKET env var)
    "last_backup_local":        None,
    "last_backup_drive":        None,
    "app_version":              "2.0",
    "custom_subjects":          [],
    "google_client_id":         "",
    "google_client_secret":     "",
    "google_redirect_uri":      "http://localhost:8501",
    "admin_email":              "",
    "google_workspace_domain":  "",
}

# Environment variable → config key mappings.
# Env vars take precedence over stored config so Cloud Run deployments
# can be configured entirely without touching the UI.
_ENV_OVERRIDES = {
    "STORAGE_MODE":           "storage_mode",
    "GCS_BUCKET":             "gcs_bucket",
    "ANTHROPIC_API_KEY":      "anthropic_api_key",
    "OPENAI_API_KEY":         "openai_api_key",
    "LOCAL_MODEL_URL":        "local_model_url",
    "LOCAL_MODEL_NAME":       "local_model_name",
    "AI_PROVIDER":            "ai_provider",
    "SCHOOL_NAME":            "school_name",
    "GOOGLE_CLIENT_ID":       "google_client_id",
    "GOOGLE_CLIENT_SECRET":   "google_client_secret",
    "GOOGLE_REDIRECT_URI":    "google_redirect_uri",
    "ADMIN_EMAIL":            "admin_email",
    "GOOGLE_WORKSPACE_DOMAIN":"google_workspace_domain",
}


def load_config() -> dict:
    saved: dict = {}

    # In GCS mode, try reading config from the bucket first.
    # We check the env var directly here to avoid a circular import with storage.py.
    if os.environ.get("STORAGE_MODE") == "gcs":
        try:
            from storage import load_remote_config
            saved = load_remote_config()
        except Exception:
            pass
    elif CONFIG_FILE.exists():
        try:
            saved = json.loads(CONFIG_FILE.read_text())
        except Exception:
            pass
    else:
        save_config(DEFAULT_CONFIG)

    cfg = {**DEFAULT_CONFIG, **saved}

    # Environment variables take final precedence (Cloud Run deployment config)
    for env_key, cfg_key in _ENV_OVERRIDES.items():
        val = os.environ.get(env_key)
        if val:
            cfg[cfg_key] = val

    return cfg


def save_config(cfg: dict):
    if os.environ.get("STORAGE_MODE") == "gcs":
        try:
            from storage import save_remote_config
            save_remote_config(cfg)
            return
        except Exception:
            pass   # fall through to local save as backup
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


def get_all_subjects(cfg: dict) -> list[str]:
    """Returns the base subject list merged with any user-added custom subjects."""
    custom = [s for s in cfg.get("custom_subjects", []) if s not in ALL_SUBJECTS]
    return ALL_SUBJECTS + custom


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def date_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")
