"""
StudioMap — Activity Logging
=============================
All user-initiated actions are logged here as structured JSONL events.
Logs are stored per-user per-day: activity/{email_hash}/YYYY-MM-DD.jsonl

This module never raises exceptions — failures are silently swallowed so that
a logging error can never crash the main application.
"""

import hashlib
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

import streamlit as st
from pydantic import BaseModel, Field


class EventType(str, Enum):
    STUDIO_UPLOAD_PDF    = "studio_upload_pdf"
    STUDIO_CREATE_MANUAL = "studio_create_manual"
    STUDIO_EDIT_SAVE     = "studio_edit_save"
    STUDIO_DELETE        = "studio_delete"
    PLAN_GENERATE        = "plan_generate"
    PLAN_SAVE            = "plan_save"
    PLAN_RATE            = "plan_rate"
    PLAN_DELETE          = "plan_delete"
    PLAN_DOWNLOAD        = "plan_download"
    SETTINGS_SAVE        = "settings_save"
    USER_LOGIN           = "user_login"
    USER_LOGOUT          = "user_logout"


class ActivityEvent(BaseModel):
    event_id:    str = Field(default_factory=lambda: uuid.uuid4().hex)
    user_email:  str
    user_name:   str
    event_type:  EventType
    timestamp:   str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    entity_id:   str = ""
    entity_name: str = ""
    metadata:    dict = {}


def email_hash(email: str) -> str:
    """Short, URL-safe, non-PII path component derived from an email address."""
    return hashlib.md5(email.lower().encode()).hexdigest()[:12]


def log_event(
    event_type: EventType,
    entity_id:   str  = "",
    entity_name: str  = "",
    metadata:    dict = None,
    user_email:  Optional[str] = None,
    user_name:   Optional[str] = None,
):
    """
    Log an activity event.

    By default reads user from st.session_state["user"].
    Pass user_email / user_name explicitly when calling from a background
    thread (which cannot access session_state).
    """
    try:
        if user_email is None:
            user       = st.session_state.get("user", {})
            user_email = user.get("email", "unknown")
            user_name  = user.get("name", user_email)

        event = ActivityEvent(
            user_email  = user_email,
            user_name   = user_name or user_email,
            event_type  = event_type,
            entity_id   = entity_id,
            entity_name = entity_name,
            metadata    = metadata or {},
        )

        import storage
        storage.append_activity(event)
    except Exception:
        pass   # logging must never crash the app
