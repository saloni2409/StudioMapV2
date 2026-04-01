"""
StudioMap — Tab 1: Studios
===========================
Manage studio profiles — upload PDFs, edit details, add coursework ideas.
"""

import threading
import uuid as _uuid
import streamlit as st
from pathlib import Path
from datetime import datetime

import storage
import ai as ai_layer
from config import ALL_GRADES, ALL_SUBJECTS, ALL_BOARDS, date_str, now_str, load_config, save_config, get_all_subjects
from models import (
    StudioProfile, Affordances, Tool, CourseworkMapping
)


# ── Import task registry (module-level, persists across Streamlit reruns) ─────
# Keyed by task_id. Each value: {status, filename, profiles, error, session_id}
# "status": "pending" | "processing" | "done" | "error"
_tasks: dict[str, dict] = {}
_tasks_lock = threading.Lock()


def _run_import_worker(task_id: str, file_bytes: bytes, file_name: str):
    """Runs in a background thread. Extracts profiles and saves them."""
    with _tasks_lock:
        _tasks[task_id]["status"] = "processing"
    try:
        profiles = ai_layer.pdf_to_profiles(file_bytes)
        saved = []
        for p in profiles:
            p.source_pdf = file_name
            path = storage.save_studio(p)
            saved.append((p.name, str(path)))
        with _tasks_lock:
            _tasks[task_id].update(status="done", profiles=saved)
    except Exception as e:
        with _tasks_lock:
            _tasks[task_id].update(status="error", error=str(e))


def _queue_import(file_bytes: bytes, file_name: str, session_id: str) -> str:
    """Register a new import task and spawn its background thread. Returns task_id."""
    task_id = _uuid.uuid4().hex
    with _tasks_lock:
        _tasks[task_id] = {
            "status":     "pending",
            "filename":   file_name,
            "profiles":   [],
            "error":      "",
            "session_id": session_id,
        }
    t = threading.Thread(target=_run_import_worker, args=(task_id, file_bytes, file_name), daemon=True)
    t.start()
    return task_id


def _get_task(task_id: str) -> dict:
    with _tasks_lock:
        return dict(_tasks.get(task_id, {}))


def _clear_tasks(task_ids: list[str]):
    with _tasks_lock:
        for tid in task_ids:
            _tasks.pop(tid, None)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mark_dirty():
    st.session_state["studios_unsaved"] = True

def _clear_dirty():
    st.session_state["studios_unsaved"] = False

def _is_dirty():
    return st.session_state.get("studios_unsaved", False)

def _clean_grades(raw: list) -> list:
    out = []
    for g in (raw or []):
        g = str(g).replace("Grade ", "").replace("grade ", "").strip()
        if g in ALL_GRADES:
            out.append(g)
    return out

def _quick_validated(p: Path) -> bool:
    try:
        import json
        return json.loads(p.read_text()).get("validated", False)
    except:
        return False

def _session_id() -> str:
    """
    Returns a stable session ID that survives page refreshes by storing it
    in the URL query param ?sid=... Streamlit preserves query params on reload.
    """
    sid = st.query_params.get("sid")
    if not sid:
        sid = _uuid.uuid4().hex
        st.query_params["sid"] = sid
    return sid


def _restore_tasks_from_registry():
    """
    On page load (including after refresh), re-populate import_task_ids from
    the module-level _tasks dict for this session. This reconnects the UI to
    any background imports that were running before the refresh.
    """
    sid = _session_id()
    with _tasks_lock:
        my_task_ids = [tid for tid, t in _tasks.items() if t.get("session_id") == sid]
    if my_task_ids:
        # Merge with any already in session state (avoids duplicates)
        existing = set(st.session_state.get("import_task_ids", []))
        merged = list(existing | set(my_task_ids))
        st.session_state["import_task_ids"] = merged


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR — called from app.py
# ══════════════════════════════════════════════════════════════════════════════

def render_sidebar():
    """Sidebar content shown when Studios page is active."""
    paths = storage.list_studios()
    validated = sum(1 for p in paths if _quick_validated(p))
    total     = len(paths)
    pct       = int(validated / total * 100) if total else 0

    st.caption(f"✅ {validated}/{total} validated ({pct}%)")
    st.progress(pct / 100)
    st.write("")

    for p in paths:
        try:
            profile = storage.load_studio(p)
            icon    = "✅" if profile.validated else "⏳"
            is_sel  = st.session_state.get("studio_path") == str(p)
            label   = f"{'▶ ' if is_sel else ''}{icon} {profile.name}"
            if st.button(label, key=f"sb_{p.stem}", use_container_width=True):
                st.session_state["studio_mode"] = "edit"
                st.session_state["studio_path"] = str(p)
                _clear_dirty()
                st.rerun()
        except Exception as e:
            st.error(f"{p.name}: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN RENDER
# ══════════════════════════════════════════════════════════════════════════════

def render():
    _restore_tasks_from_registry()
    mode = st.session_state.get("studio_mode", "list")

    if mode == "edit" and st.session_state.get("studio_path"):
        _render_edit_studio(Path(st.session_state["studio_path"]))
    else:
        _render_studio_list()


# ── Studio list (home) ────────────────────────────────────────────────────────

def _render_studio_list():
    paths = storage.list_studios()

    # Header row
    col_title, col_btn = st.columns([4, 1])
    with col_title:
        st.markdown("## 🏫 Studios")
    with col_btn:
        st.write("")
        if st.button("➕ New Studio", type="primary", use_container_width=True):
            st.session_state["show_add_studio_dialog"] = True

    # ── Persistent import queue (visible even after dialog closes) ────────
    task_ids = st.session_state.get("import_task_ids", [])
    if task_ids:
        _render_import_queue(task_ids, inside_dialog=False)

    # ── New Studio Dialog ─────────────────────────────────────────────────
    if st.session_state.get("show_add_studio_dialog"):
        _render_add_studio_dialog()

    st.divider()

    # ── Studio grid ───────────────────────────────────────────────────────
    if not paths:
        st.info("No studios yet. Click **➕ New Studio** to get started.")
        return

    cols = st.columns(3)
    for i, p in enumerate(paths):
        try:
            profile = storage.load_studio(p)
            with cols[i % 3]:
                icon = "✅" if profile.validated else "⏳"
                with st.container(border=True):
                    st.markdown(f"**{icon} {profile.name}**")
                    if profile.tagline:
                        st.caption(profile.tagline)
                    st.caption(profile.grade_label())
                    btn_col, del_col = st.columns([3, 1])
                    with btn_col:
                        if st.button("Edit →", key=f"open_{p.stem}", use_container_width=True):
                            st.session_state["studio_mode"] = "edit"
                            st.session_state["studio_path"] = str(p)
                            _clear_dirty()
                            st.rerun()
                    with del_col:
                        if st.button("🗑️", key=f"del_card_{p.stem}",
                                     help=f"Delete '{profile.name}'"):
                            st.session_state[f"confirm_del_{p.stem}"] = True
                            st.rerun()
                    # Confirm delete
                    if st.session_state.get(f"confirm_del_{p.stem}"):
                        st.warning(f"Delete **{profile.name}**? This cannot be undone.")
                        c1, c2 = st.columns(2)
                        with c1:
                            if st.button("Yes, delete", key=f"yes_del_{p.stem}",
                                         type="primary", use_container_width=True):
                                storage.delete_studio(p)
                                st.session_state.pop(f"confirm_del_{p.stem}", None)
                                st.rerun()
                        with c2:
                            if st.button("Cancel", key=f"cancel_del_{p.stem}",
                                         use_container_width=True):
                                st.session_state.pop(f"confirm_del_{p.stem}", None)
                                st.rerun()
        except Exception as e:
            st.error(f"{p.name}: {e}")


# ── Import queue panel ────────────────────────────────────────────────────────

def _render_import_queue(task_ids: list[str], inside_dialog: bool = True):
    """Renders the import progress panel. Called from dialog and list view."""
    tasks = [_get_task(tid) for tid in task_ids]
    if not tasks:
        return

    STATUS_ICON = {"pending": "⏳", "processing": "🔄", "done": "✅", "error": "❌"}

    any_running = any(t.get("status") in ("pending", "processing") for t in tasks)
    all_done    = all(t.get("status") in ("done", "error") for t in tasks)

    with st.container(border=True):
        hdr_col, btn_col = st.columns([4, 1])
        with hdr_col:
            st.markdown("**Import Queue**")
        with btn_col:
            if any_running:
                if st.button("↻ Refresh", key=f"refresh_queue_{'d' if inside_dialog else 'l'}"):
                    st.rerun()
            elif all_done:
                if st.button("Clear", key=f"clear_queue_{'d' if inside_dialog else 'l'}"):
                    _clear_tasks(task_ids)
                    st.session_state.pop("import_task_ids", None)
                    st.rerun()

        for task in tasks:
            status   = task.get("status", "pending")
            icon     = STATUS_ICON.get(status, "⏳")
            filename = task.get("filename", "unknown")

            if status == "done":
                profiles = task.get("profiles", [])
                names    = ", ".join(n for n, _ in profiles) if profiles else "—"
                st.success(f"{icon} **{filename}** → {len(profiles)} studio(s): {names}")
            elif status == "error":
                st.error(f"{icon} **{filename}** — {task.get('error', 'Unknown error')}")
                st.caption("Check your AI provider settings or try manual creation.")
            elif status == "processing":
                st.info(f"{icon} **{filename}** — Extracting with AI…")
            else:
                st.caption(f"{icon} **{filename}** — Queued")

    # Auto-redirect: if exactly 1 studio total imported and all done
    if all_done and not inside_dialog:
        all_profiles = [p for t in tasks for p in t.get("profiles", [])]
        errors = [t for t in tasks if t.get("status") == "error"]
        if len(all_profiles) == 1 and not errors:
            name, path = all_profiles[0]
            _clear_tasks(task_ids)
            st.session_state.pop("import_task_ids", None)
            st.session_state["studio_mode"] = "edit"
            st.session_state["studio_path"] = path
            _clear_dirty()
            st.rerun()


# ── Add Studio dialog ─────────────────────────────────────────────────────────

@st.dialog("➕ Add New Studio")
def _render_add_studio_dialog():
    cfg     = load_config()
    ai_name = {"anthropic": "Claude", "openai": "ChatGPT", "local": cfg.get("local_model_name","Local Model")}.get(
        cfg.get("ai_provider", "anthropic"), "AI"
    )

    # Cancel button — clears flag so dialog won't reopen on next rerun/navigation
    _, cancel_col = st.columns([5, 1])
    with cancel_col:
        if st.button("✕ Cancel", key="cancel_add_dialog", use_container_width=True):
            st.session_state.pop("show_add_studio_dialog", None)
            st.rerun()

    tab_pdf, tab_manual = st.tabs([f"📄 Upload PDF ({ai_name})", "✏️ Create Manually"])

    with tab_pdf:
        st.caption(f"{ai_name} will read the PDFs and fill in the profiles automatically.")
        st.caption("PDFs with multiple studios will create a separate profile for each one.")

        uploaded_files = st.file_uploader(
            "Upload one or more studio documentation PDFs",
            type=["pdf"], key="dialog_pdf_upload",
            accept_multiple_files=True
        )

        # Show existing queue if any
        existing_task_ids = st.session_state.get("import_task_ids", [])
        if existing_task_ids:
            _render_import_queue(existing_task_ids, inside_dialog=True)

        if uploaded_files:
            btn_label = f"⚡ Import {len(uploaded_files)} PDF(s)"
            if existing_task_ids:
                btn_label = f"⚡ Add {len(uploaded_files)} More PDF(s) to Queue"

            if st.button(btn_label, type="primary"):
                sid = _session_id()
                new_task_ids = []
                for file in uploaded_files:
                    file.seek(0)
                    task_id = _queue_import(file.read(), file.name, sid)
                    new_task_ids.append(task_id)

                # Merge with any existing task IDs
                all_ids = existing_task_ids + new_task_ids
                st.session_state["import_task_ids"] = all_ids
                st.session_state.pop("show_add_studio_dialog", None)
                st.rerun()

    with tab_manual:
        name = st.text_input("Studio Name *", placeholder="e.g. Duolingo Lab", key="new_studio_name")
        sid  = st.text_input("Studio ID",     placeholder="e.g. S07",           key="new_studio_id")

        if st.button("Create Studio", type="primary", key="create_manual_btn"):
            if not name.strip():
                st.error("Name is required.")
            else:
                profile = StudioProfile(name=name.strip(), studio_id=sid.strip())
                path    = storage.save_studio(profile)
                st.success(f"✅ '{name}' created.")
                st.session_state["studio_mode"] = "edit"
                st.session_state["studio_path"] = str(path)
                st.session_state.pop("show_add_studio_dialog", None)
                _clear_dirty()
                st.rerun()


# ── Edit studio ───────────────────────────────────────────────────────────────

def _render_edit_studio(path: Path):
    try:
        profile = storage.load_studio(path)
    except Exception as e:
        st.error(f"Could not load studio: {e}")
        return

    # Top nav
    c1, c2 = st.columns([1, 8])
    with c1:
        if st.button("← Back"):
            st.session_state["studio_mode"] = "list"
            st.rerun()
    with c2:
        badge = "✅ Validated" if profile.validated else "⏳ Pending Review"
        st.markdown(f"### {profile.name}  `{badge}`")

    if _is_dirty():
        st.warning("⚠️ Unsaved changes — click Save at the bottom.")

    t1, t2, t3, t4 = st.tabs([
        "🏷️ Profile", "🔧 Tools", "📝 Coursework", "🖼️ Images"
    ])

    with t1:
        profile = _tab_profile(profile, path)
    with t2:
        profile = _tab_tools(profile, path)
    with t3:
        profile = _tab_coursework(profile, path)
    with t4:
        profile = _tab_images(profile, path)

    st.divider()
    _save_bar(profile, path)


# ── Tab: Profile ──────────────────────────────────────────────────────────────

def _tab_profile(profile: StudioProfile, path: Path) -> StudioProfile:
    c1, c2 = st.columns(2)
    with c1:
        v = profile.studio_id
        nv = st.text_input("Studio ID", value=v, key=f"sid_{path.stem}")
        if nv != v: profile.studio_id = nv; _mark_dirty()
    with c2:
        v = profile.name
        nv = st.text_input("Studio Name *", value=v, key=f"sname_{path.stem}")
        if nv != v: profile.name = nv; _mark_dirty()

    v = profile.tagline
    nv = st.text_input("Tagline", value=v, key=f"tag_{path.stem}",
                        placeholder="One sentence that captures this studio's unique value")
    if nv != v: profile.tagline = nv; _mark_dirty()

    v = profile.description
    nv = st.text_area("Description", value=v, height=120, key=f"desc_{path.stem}",
                       placeholder="2-3 paragraphs. What is this space? What makes it different?")
    if nv != v: profile.description = nv; _mark_dirty()

    st.markdown("##### What This Space Enables")
    st.caption("This is the most important section — the AI uses this to match studios to topics.")

    v = profile.affordances.summary
    nv = st.text_area("Affordances Summary *", value=v, height=100,
                       key=f"aff_sum_{path.stem}",
                       placeholder="Describe what students CAN DO here — not just what's in the room.")
    if nv != v: profile.affordances.summary = nv; _mark_dirty()

    cols = st.columns(4)
    fields = [
        ("individual_work",  "Individual Work"),
        ("pair_work",        "Pair Work"),
        ("group_work",       "Group Work"),
        ("movement",         "Student Movement"),
        ("digital_practice", "Digital Practice"),
        ("physical_making",  "Physical Making"),
        ("presentation",     "Presentation"),
        ("self_assessment",  "Self Assessment"),
    ]
    for i, (field, label) in enumerate(fields):
        with cols[i % 4]:
            v  = getattr(profile.affordances, field)
            nv = st.checkbox(label, value=v, key=f"aff_{field}_{path.stem}")
            if nv != v:
                setattr(profile.affordances, field, nv); _mark_dirty()

    st.markdown("##### Scope")
    c1, c2, c3 = st.columns(3)
    with c1:
        v  = _clean_grades(profile.grades)
        nv = st.multiselect("Grades", ALL_GRADES, default=v, key=f"grades_{path.stem}")
        if nv != v: profile.grades = nv; _mark_dirty()
    with c2:
        _cfg = load_config()
        effective_subjects = get_all_subjects(_cfg)
        unknown = [s for s in profile.subjects if s not in effective_subjects]
        for subj in unknown:
            uc1, uc2 = st.columns([4, 1])
            uc1.warning(f'"{subj}" is not in the subjects list (extracted by AI).')
            if uc2.button(f'Add "{subj}"', key=f"add_subj_{subj}_{path.stem}"):
                _cfg["custom_subjects"] = _cfg.get("custom_subjects", []) + [subj]
                save_config(_cfg)
                st.rerun()
        safe_default = [s for s in profile.subjects if s in effective_subjects]
        nv = st.multiselect("Subjects", effective_subjects, default=safe_default, key=f"subj_{path.stem}")
        if nv != profile.subjects: profile.subjects = nv; _mark_dirty()
    with c3:
        v  = profile.board
        nv = st.selectbox("Board", ALL_BOARDS,
                           index=ALL_BOARDS.index(v) if v in ALL_BOARDS else 0,
                           key=f"board_{path.stem}")
        if nv != v: profile.board = nv; _mark_dirty()

    st.markdown("##### Physical Details")
    c1, c2 = st.columns(2)
    with c1:
        v  = profile.area_sqft or 0
        nv = st.number_input("Area (sq ft)", value=int(v), min_value=0, step=50,
                              key=f"area_{path.stem}")
        if nv != v: profile.area_sqft = nv or None; _mark_dirty()
    with c2:
        v  = profile.capacity or 0
        nv = st.number_input("Student Capacity", value=int(v), min_value=0, step=5,
                              key=f"cap_{path.stem}")
        if nv != v: profile.capacity = nv or None; _mark_dirty()

    c1, c2 = st.columns(2)
    with c1:
        v  = profile.lighting
        nv = st.text_input("Lighting", value=v, key=f"light_{path.stem}")
        if nv != v: profile.lighting = nv; _mark_dirty()
    with c2:
        v  = profile.ventilation
        nv = st.text_input("Ventilation", value=v, key=f"vent_{path.stem}")
        if nv != v: profile.ventilation = nv; _mark_dirty()

    # Show AI raw observations (from photos/diagrams) if present
    if profile.raw_notes:
        with st.expander("🔍 AI Raw Observations (from photos & diagrams)", expanded=False):
            st.caption("Everything the AI noticed from images and diagrams that didn't fit the structured fields above.")
            v  = profile.raw_notes
            nv = st.text_area("Raw Notes", value=v, height=150, key=f"raw_{path.stem}",
                               label_visibility="collapsed")
            if nv != v: profile.raw_notes = nv; _mark_dirty()

    return profile


# ── Tab: Tools ────────────────────────────────────────────────────────────────

def _tab_tools(profile: StudioProfile, path: Path) -> StudioProfile:
    st.caption("Each physical tool or installation. Be specific about how students interact with each one.")

    if st.button("➕ Add Tool", key=f"add_tool_{path.stem}"):
        profile.tools.append(Tool(name="New Tool"))
        _mark_dirty()

    to_delete = []
    for i, tool in enumerate(profile.tools):
        with st.expander(f"🔧 {tool.name or f'Tool {i+1}'}", expanded=(i == 0)):
            c1, c2 = st.columns([2, 1])
            with c1:
                tool.name = st.text_input("Name", value=tool.name, key=f"tn_{i}_{path.stem}")
            with c2:
                tool.quantity = st.number_input("Qty", value=tool.quantity,
                                                 min_value=1, key=f"tq_{i}_{path.stem}")
            tool.description = st.text_area("Description", value=tool.description,
                                             height=60, key=f"td_{i}_{path.stem}")
            c1, c2, c3 = st.columns(3)
            with c1:
                tool.dimensions = st.text_input("Dimensions",
                    value=tool.dimensions, key=f"tdim_{i}_{path.stem}")
            with c2:
                tool.movable = st.checkbox("Movable?",
                    value=tool.movable, key=f"tmov_{i}_{path.stem}")
            with c3:
                pass
            tool.interaction = st.text_input(
                "How do students use this?",
                value=tool.interaction, key=f"tint_{i}_{path.stem}",
                placeholder="e.g. Students write on it in pairs, racing to complete the task"
            )
            if st.button("🗑️ Delete", key=f"del_tool_{i}_{path.stem}"):
                to_delete.append(i); _mark_dirty()

    for idx in sorted(to_delete, reverse=True):
        profile.tools.pop(idx)
    return profile


# ── Tab: Coursework ───────────────────────────────────────────────────────────

def _tab_coursework(profile: StudioProfile, path: Path) -> StudioProfile:
    st.caption("Sample teaching ideas using this studio. These train the AI to give better suggestions.")

    with st.expander("➕ Add New Idea", expanded=(len(profile.coursework) == 0)):
        topic   = st.text_input("Topic / Chapter *", placeholder="e.g. Forms of Verbs",
                                 key=f"new_topic_{path.stem}")
        c1, c2, c3 = st.columns(3)
        with c1:
            subject = st.selectbox("Subject", ALL_SUBJECTS, key=f"new_subj_{path.stem}")
        with c2:
            grades = st.multiselect("Grade(s)", ALL_GRADES, key=f"new_grades_{path.stem}")
        with c3:
            sessions = st.number_input("Sessions", min_value=1, value=1, key=f"new_sess_{path.stem}")
        plan = st.text_area("Teaching Plan *", height=150,
                             placeholder="Session 1 — How you use specific tools...",
                             key=f"new_plan_{path.stem}")
        notes = st.text_input("Teacher Notes", placeholder="e.g. Pre-sort materials before class",
                               key=f"new_notes_{path.stem}")

        if st.button("✅ Add Idea", type="primary", key=f"add_cw_{path.stem}"):
            if not topic.strip() or not plan.strip():
                st.error("Topic and Teaching Plan are required.")
            else:
                profile.coursework.append(CourseworkMapping(
                    topic=topic.strip(), subject=subject, grades=grades,
                    sessions=sessions, teaching_plan=plan.strip(),
                    teacher_notes=notes.strip(),
                    added_by=st.session_state.get("reviewer_name", ""),
                    added_date=date_str()
                ))
                _mark_dirty()
                st.success("✅ Added!")
                st.rerun()

    st.divider()
    if not profile.coursework:
        st.info("No ideas yet — add one above.")
        return profile

    to_delete = []
    for i, cw in enumerate(profile.coursework):
        grades_str = ", ".join(cw.grades) if cw.grades else "—"
        stars      = "⭐" * cw.rating if cw.rating else ""
        label      = f"📝 {cw.topic}  ·  {cw.subject}  ·  Grade {grades_str}  {stars}"
        with st.expander(label):
            cw.topic = st.text_input("Topic", value=cw.topic, key=f"cw_topic_{i}_{path.stem}")
            c1, c2 = st.columns(2)
            with c1:
                cw.subject = st.selectbox("Subject", ALL_SUBJECTS,
                    index=ALL_SUBJECTS.index(cw.subject) if cw.subject in ALL_SUBJECTS else 0,
                    key=f"cw_subj_{i}_{path.stem}")
                cw.sessions = st.number_input("Sessions", value=cw.sessions,
                    min_value=1, key=f"cw_sess_{i}_{path.stem}")
            with c2:
                cw.grades = st.multiselect("Grades", ALL_GRADES,
                    default=_clean_grades(cw.grades), key=f"cw_grades_{i}_{path.stem}")
                if cw.rating:
                    st.caption(f"Rating: {'⭐' * cw.rating}")
            cw.teaching_plan = st.text_area("Teaching Plan", value=cw.teaching_plan,
                height=120, key=f"cw_plan_{i}_{path.stem}")
            cw.teacher_notes = st.text_input("Teacher Notes", value=cw.teacher_notes,
                key=f"cw_notes_{i}_{path.stem}")
            if st.button("🗑️ Remove", key=f"del_cw_{i}_{path.stem}"):
                to_delete.append(i); _mark_dirty()

    for idx in sorted(to_delete, reverse=True):
        profile.coursework.pop(idx)
    return profile


# ── Tab: Images ───────────────────────────────────────────────────────────────

def _tab_images(profile: StudioProfile, path: Path) -> StudioProfile:
    st.caption("Photos of the studio space.")
    uploaded = st.file_uploader("Upload images", type=["jpg","jpeg","png","webp"],
                                 accept_multiple_files=True, key=f"imgs_{path.stem}")
    if uploaded:
        for f in uploaded:
            fname = f"{path.stem}_{datetime.now().strftime('%H%M%S%f')}{Path(f.name).suffix}"
            rel   = storage.save_image(f.read(), fname)
            if rel not in profile.images:
                profile.images.append(rel)
                _mark_dirty()
        st.success(f"✅ {len(uploaded)} image(s) added")

    if profile.images:
        cols = st.columns(4)
        to_remove = []
        for i, rel in enumerate(profile.images):
            p = storage.image_path(rel)
            if p.exists():
                with cols[i % 4]:
                    st.image(str(p), use_column_width=True)
                    if st.button("🗑️", key=f"del_img_{i}_{path.stem}"):
                        to_remove.append(rel); _mark_dirty()
        profile.images = [x for x in profile.images if x not in to_remove]

    return profile


# ── Save bar ─────────────────────────────────────────────────────────────────

def _save_bar(profile: StudioProfile, path: Path):
    if _is_dirty():
        st.warning("⚠️ Unsaved changes")

    c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 1])
    with c1:
        name = st.text_input("Reviewer", value=profile.reviewed_by,
                              placeholder="Your name", key=f"rev_{path.stem}")
        profile.reviewed_by = name
        st.session_state["reviewer_name"] = name
    with c2:
        st.write("")
        profile.validated = st.checkbox("✅ Validated",
            value=profile.validated, key=f"val_{path.stem}")
    with c3:
        st.write(""); st.write("")
        if st.button("💾 Save", type="primary", key=f"save_{path.stem}",
                      use_container_width=True):
            profile.reviewed_date = now_str()
            storage.save_studio(profile, path)
            _clear_dirty()
            st.success("Saved!")
            st.rerun()
    with c4:
        st.write(""); st.write("")
        st.download_button("📥 Export",
            data=profile.model_dump_json(indent=2),
            file_name=path.name,
            mime="application/json",
            use_container_width=True,
            key=f"exp_{path.stem}"
        )
    with c5:
        st.write(""); st.write("")
        if st.button("🗑️ Delete", key=f"del_studio_{path.stem}",
                      use_container_width=True):
            st.session_state[f"confirm_del_edit_{path.stem}"] = True

    # Inline delete confirmation
    if st.session_state.get(f"confirm_del_edit_{path.stem}"):
        st.error(f"⚠️ Permanently delete **{profile.name}**? This cannot be undone.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("✅ Yes, delete permanently", key=f"yes_del_edit_{path.stem}",
                          type="primary", use_container_width=True):
                storage.delete_studio(path)
                st.session_state["studio_mode"] = "list"
                st.session_state.pop("studio_path", None)
                st.session_state.pop(f"confirm_del_edit_{path.stem}", None)
                st.rerun()
        with c2:
            if st.button("Cancel", key=f"cancel_del_edit_{path.stem}",
                          use_container_width=True):
                st.session_state.pop(f"confirm_del_edit_{path.stem}", None)
                st.rerun()
