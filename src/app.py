"""
StudioMap v2
=============
AI-powered studio knowledge base and lesson plan generator for experiential learning schools.

Run:
    pip install -r requirements.txt
    streamlit run src/app.py
"""

import streamlit as st
import sys
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

from config import load_config
import studios
import generate
import explore
import settings as settings_tab

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="StudioMap",
    page_icon="🏫",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Hide default Streamlit header padding */
    .block-container { padding-top: 1.5rem; }

    /* Sidebar nav buttons */
    div[data-testid="stSidebar"] .stButton > button {
        background: transparent;
        border: none;
        text-align: left;
        font-size: 1rem;
        padding: 0.5rem 0.75rem;
        border-radius: 8px;
        width: 100%;
        color: inherit;
        transition: background 0.15s;
    }
    div[data-testid="stSidebar"] .stButton > button:hover {
        background: rgba(79, 70, 229, 0.1);
    }

    /* Active nav button highlight */
    .nav-active > button {
        background: rgba(79, 70, 229, 0.15) !important;
        color: #4F46E5 !important;
        font-weight: 600 !important;
    }

    /* Page header */
    .app-header {
        background: linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%);
        padding: 1rem 1.5rem; border-radius: 10px;
        margin-bottom: 1.5rem;
    }
    .app-header h1 { color: white; margin: 0; font-size: 1.4rem; }
    .app-header p  { color: rgba(255,255,255,0.75); margin: 0; font-size: 0.85rem; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR NAVIGATION
# ══════════════════════════════════════════════════════════════════════════════

NAV_PAGES = [
    ("🏫 Studios",  "studios"),
    ("✨ Generate", "generate"),
    ("🔍 Explore",  "explore"),
    ("⚙️ Settings", "settings"),
]

def _render_sidebar_nav(active: str, cfg: dict):
    school_name = cfg.get("school_name") or "StudioMap"
    mode_icon   = "☁️" if cfg.get("storage_mode") == "drive" else "💾"

    st.markdown(f"### 🏫 {school_name}")
    st.caption(f"{mode_icon} {cfg.get('storage_mode','local').title()} Storage")
    st.divider()

    for label, page_key in NAV_PAGES:
        is_active = active == page_key
        # Inject class for active styling via a container
        container = st.container()
        if is_active:
            container.markdown('<div class="nav-active">', unsafe_allow_html=True)
        with container:
            if st.button(label, key=f"nav_{page_key}", use_container_width=True):
                st.session_state["active_page"] = page_key
                # Clear sub-page state when changing pages
                if page_key == "studios":
                    st.session_state["studio_mode"] = "list"
                    st.session_state.pop("show_add_studio_dialog", None)
                st.rerun()
        if is_active:
            container.markdown('</div>', unsafe_allow_html=True)

    st.divider()

    # ── Studio-specific sidebar (quick list) ──────────────────────────────
    if active == "studios":
        studios.render_sidebar()

    # ── Explore-specific sidebar is now inline — nothing here ─────────────


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    # Session state defaults
    if "active_page"     not in st.session_state: st.session_state["active_page"]     = "studios"
    if "studio_mode"     not in st.session_state: st.session_state["studio_mode"]     = "list"
    if "studios_unsaved" not in st.session_state: st.session_state["studios_unsaved"] = False

    cfg         = load_config()
    active_page = st.session_state["active_page"]

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        _render_sidebar_nav(active_page, cfg)

    # ── Main content ──────────────────────────────────────────────────────────
    if active_page == "studios":
        studios.render()
    elif active_page == "generate":
        if "prefill_topic" in st.session_state:
            st.session_state["generate_prefill"] = True
        generate.render()
    elif active_page == "explore":
        explore.render()
    elif active_page == "settings":
        settings_tab.render()


if __name__ == "__main__":
    main()
