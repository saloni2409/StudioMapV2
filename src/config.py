"""
StudioMap — Configuration
==========================
Single source of truth for all paths, constants, and settings.
Nothing is hardcoded anywhere else — everything comes from here.
"""

from pathlib import Path
import json
from datetime import datetime

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent.parent
DATA_DIR    = BASE_DIR / "data"
STUDIOS_DIR = DATA_DIR / "studios"
PLANS_DIR   = DATA_DIR / "plans"
UPLOADS_DIR = DATA_DIR / "uploads"
IMAGES_DIR  = DATA_DIR / "images"
CONFIG_FILE = DATA_DIR / "config.json"
CREDS_FILE  = BASE_DIR / "credentials.json"   # Google Drive service account key

# Create all directories on import
for _d in [STUDIOS_DIR, PLANS_DIR, UPLOADS_DIR, IMAGES_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# ── AI ────────────────────────────────────────────────────────────────────────
CLAUDE_MODEL    = "claude-sonnet-4-20250514"
OPENAI_MODEL    = "gpt-4o"
MAX_TOKENS      = 4096
PDF_MAX_TOKENS  = 4096   # for PDF → profile extraction

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
    "last_backup_local":      None,
    "last_backup_drive":      None,
    "app_version":            "2.0"
}


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            saved = json.loads(CONFIG_FILE.read_text())
            return {**DEFAULT_CONFIG, **saved}
        except Exception:
            pass
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG.copy()


def save_config(cfg: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def date_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")
