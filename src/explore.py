"""
StudioMap — Tab 3: Explore
===========================
Browse, filter, and reuse saved lesson plans.
Filters are shown inline on the page (not in sidebar).
"""

import streamlit as st
from pathlib import Path
from collections import defaultdict

import storage
from config import ALL_GRADES, ALL_SUBJECTS, load_config, get_all_subjects
from models import LessonPlan


def render():
    plans = _load_all_plans()

    st.markdown("## 🔍 Explore Lesson Plans")

    if not plans:
        st.info("No saved plans yet. Go to **✨ Generate** and create some!")
        return

    # ── Inline filter row ─────────────────────────────────────────────────────
    with st.container(border=True):
        st.caption("🔎 Filters")
        c1, c2, c3, c4, c5, c6 = st.columns([2, 2, 2, 2, 1, 2])

        all_grades   = sorted({p.grade for p in plans}, key=lambda g: int(g))
        all_subjects = sorted({p.subject for p in plans})
        all_studios  = sorted({name for p in plans for name in p.studio_names})
        all_boards   = sorted({p.board for p in plans})

        with c1:
            f_grade = st.multiselect("Grade", all_grades, key="f_grade", label_visibility="collapsed",
                                     placeholder="All Grades")
        with c2:
            f_subject = st.multiselect("Subject", all_subjects, key="f_subject", label_visibility="collapsed",
                                       placeholder="All Subjects")
        with c3:
            f_studio = st.multiselect("Studio", all_studios, key="f_studio", label_visibility="collapsed",
                                      placeholder="All Studios")
        with c4:
            f_board = st.multiselect("Board", all_boards, key="f_board", label_visibility="collapsed",
                                     placeholder="All Boards")
        with c5:
            f_rating = st.selectbox("Min ⭐", [0,1,2,3,4,5], format_func=lambda x: f"{'⭐'*x or 'Any'}", 
                                    key="f_rating", label_visibility="collapsed")
        with c6:
            f_search = st.text_input("Search", placeholder="Search topic...", key="f_search",
                                     label_visibility="collapsed")

        if st.button("✖ Clear Filters", key="clear_filters"):
            for k in ["f_grade","f_subject","f_studio","f_board","f_rating","f_search"]:
                if k in st.session_state:
                    del st.session_state[k]
            st.rerun()

    # ── Apply filters ─────────────────────────────────────────────────────────
    filtered = _apply_filters(plans)

    # ── Stats row ─────────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Total Plans", len(plans))
    with c2:
        st.metric("Showing", len(filtered))
    with c3:
        rated = [p for p in plans if p.rating]
        avg   = sum(p.rating for p in rated) / len(rated) if rated else 0
        st.metric("Avg Rating", f"{'⭐' * round(avg)}" if avg else "—")
    with c4:
        studios_covered = len({s for p in plans for s in p.studio_ids})
        st.metric("Studios Used", studios_covered)

    # ── View toggle ───────────────────────────────────────────────────────────
    view = st.radio("View", ["📋 Plans", "📊 Coverage Gaps"],
                     horizontal=True, label_visibility="collapsed")
    st.divider()

    if view == "📋 Plans":
        _render_plan_list(filtered)
    else:
        _render_coverage_gaps(plans)


def _apply_filters(plans: list[LessonPlan]) -> list[LessonPlan]:
    grades   = st.session_state.get("f_grade",   [])
    subjects = st.session_state.get("f_subject", [])
    studios  = st.session_state.get("f_studio",  [])
    boards   = st.session_state.get("f_board",   [])
    min_rat  = st.session_state.get("f_rating",  0)
    search   = st.session_state.get("f_search",  "").lower().strip()

    out = plans
    if grades:    out = [p for p in out if p.grade in grades]
    if subjects:  out = [p for p in out if p.subject in subjects]
    if studios:   out = [p for p in out if any(s in p.studio_names for s in studios)]
    if boards:    out = [p for p in out if p.board in boards]
    if min_rat:   out = [p for p in out if (p.rating or 0) >= min_rat]
    if search:    out = [p for p in out if search in p.topic.lower() or search in p.subject.lower()]
    return out


# ── Plan list ─────────────────────────────────────────────────────────────────

def _render_plan_list(plans: list[LessonPlan]):
    if not plans:
        st.info("No plans match the current filters.")
        return

    for plan in plans:
        _render_plan_card(plan)


def _render_plan_card(plan: LessonPlan):
    stars       = "⭐" * plan.rating if plan.rating else "not rated"
    studios_str = " + ".join(plan.studio_names) if plan.studio_names else "—"
    label = f"**{plan.topic}** · Grade {plan.grade} · {plan.subject} · {stars}"

    with st.expander(label):
        st.caption(f"Studios: {studios_str}  ·  {plan.sessions} session(s)  "
                   f"·  {plan.board}  ·  {plan.generated_date}")

        if plan.objectives:
            st.markdown("**Learning Objectives**")
            for obj in plan.objectives:
                st.markdown(f"- {obj}")

        st.markdown(plan.plan_text)
        st.divider()

        c1, c2, c3 = st.columns(3)
        with c1:
            new_rating = st.feedback("stars", key=f"rate_{plan.plan_id}")
            if new_rating is not None and (new_rating + 1) != plan.rating:
                plan.rating = new_rating + 1
                storage.save_plan(plan)
                st.rerun()
        with c2:
            st.download_button(
                "📥 Download",
                data=plan.plan_text,
                file_name=f"{plan.topic.lower().replace(' ','_')}_g{plan.grade}.md",
                mime="text/markdown",
                key=f"dl_{plan.plan_id}"
            )
        with c3:
            if st.button("🗑️ Delete", key=f"del_{plan.plan_id}"):
                path = storage.PLANS_DIR / plan.filename()
                storage.delete_plan(path)
                st.rerun()

        if st.button("🔄 Use as Starting Point", key=f"reuse_{plan.plan_id}",
                      help="Pre-fills the Generate tab with this topic and grade"):
            st.session_state["prefill_topic"]   = plan.topic
            st.session_state["prefill_subject"]  = plan.subject
            st.session_state["prefill_grade"]    = plan.grade
            st.session_state["active_page"]      = "generate"
            st.rerun()


# ── Coverage gaps ─────────────────────────────────────────────────────────────

def _render_coverage_gaps(plans: list[LessonPlan]):
    st.markdown("#### Coverage Gaps")
    st.caption("Shows where lesson plans have not been created yet.")

    covered        = defaultdict(set)
    for p in plans:
        covered[p.grade].add(p.subject)

    subjects_seen = sorted({p.subject for p in plans})
    grades_seen   = sorted({p.grade for p in plans}, key=lambda g: int(g))

    if not grades_seen:
        st.info("No plans yet.")
        return

    header = ["Grade"] + subjects_seen
    rows   = []
    for g in grades_seen:
        row = [f"Grade {g}"]
        for s in subjects_seen:
            row.append("✅" if s in covered[g] else "—")
        rows.append(row)

    import pandas as pd
    df = pd.DataFrame(rows, columns=header)
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("#### Studios Used")
    studio_counts = defaultdict(int)
    for p in plans:
        for name in p.studio_names:
            studio_counts[name] += 1

    all_studio_paths = storage.list_studios()
    all_studio_names = set()
    for sp in all_studio_paths:
        try:
            all_studio_names.add(storage.load_studio(sp).name)
        except:
            pass

    used_studios   = set(studio_counts.keys())
    unused_studios = all_studio_names - used_studios

    if unused_studios:
        st.warning(f"**{len(unused_studios)} studio(s) have no lesson plans yet:**")
        for name in sorted(unused_studios):
            st.markdown(f"  - {name}")
    else:
        st.success("All studios have at least one lesson plan!")

    if studio_counts:
        st.markdown("**Plans per studio:**")
        for name, count in sorted(studio_counts.items(), key=lambda x: -x[1]):
            st.progress(count / max(studio_counts.values()),
                        text=f"{name}: {count} plan(s)")


# ── Load ──────────────────────────────────────────────────────────────────────

def _load_all_plans() -> list[LessonPlan]:
    plans = []
    for p in storage.list_plans():
        try:
            plans.append(storage.load_plan(p))
        except:
            pass
    return sorted(plans, key=lambda p: p.generated_date, reverse=True)
