"""
StudioMap — Tab 2: Generate
============================
Teachers use this to generate lesson plans grounded in their actual studios.
Simple flow: pick studios → enter topic + grade → generate → rate → save.
"""

import streamlit as st
from pathlib import Path

import storage
import ai as ai_layer
import activity as act
from config import ALL_GRADES, ALL_SUBJECTS, ALL_BOARDS, date_str, load_config, get_all_subjects
from models import LessonPlan


def render():
    st.markdown("### ✨ Generate Lesson Plan")
    st.caption("The AI uses your actual studio tools and affordances to create plans specific to your school.")

    studios = _load_all_studios()
    if not studios:
        st.warning("No studios set up yet. Go to the **Studios** tab and add some first.")
        return

    # ── Form ─────────────────────────────────────────────────────────────────
    with st.form("generate_form"):
        st.markdown("#### What do you want to teach?")

        c1, c2, c3 = st.columns(3)
        with c1:
            topic = st.text_input("Topic / Chapter *",
                placeholder="e.g. Forms of Verbs, Trigonometry, Water Cycle")
        with c2:
            subject = st.selectbox("Subject", get_all_subjects(load_config()))
        with c3:
            grade = st.selectbox("Grade", ALL_GRADES, index=4)

        c1, c2 = st.columns(2)
        with c1:
            board = st.selectbox("Board", ALL_BOARDS)
        with c2:
            sessions = st.number_input("Number of Sessions", min_value=1,
                                        max_value=10, value=1)

        st.markdown("#### Which studios?")
        st.caption("Select one or more. For multi-studio lessons, the AI creates a journey across them.")

        studio_names = {p.stem: s.name for p, s in studios}
        selected = st.multiselect(
            "Studios",
            options=list(studio_names.keys()),
            format_func=lambda k: studio_names[k],
            default=[list(studio_names.keys())[0]] if studio_names else []
        )

        teacher_name = st.text_input("Your Name (optional)", value=
                                      st.session_state.get("reviewer_name", ""))

        submitted = st.form_submit_button("✨ Generate Plan", type="primary",
                                           use_container_width=True)

    # ── Generate ──────────────────────────────────────────────────────────────
    if submitted:
        if not topic.strip():
            st.error("Please enter a topic.")
            return
        if not selected:
            st.error("Please select at least one studio.")
            return

        selected_studios = [s for p, s in studios if p.stem in selected]
        similar_plans    = _find_similar_plans(subject, grade)

        with st.spinner("Generating lesson plan..."):
            try:
                plan_text = ai_layer.generate_plan(
                    topic=topic.strip(),
                    subject=subject,
                    grade=grade,
                    board=board,
                    sessions=sessions,
                    studios=selected_studios,
                    similar_plans=similar_plans
                )
                objectives = ai_layer.extract_objectives(plan_text)

                user        = st.session_state.get("user", {})
                user_email  = user.get("email", "")
                plan = LessonPlan(
                    topic=topic.strip(),
                    subject=subject,
                    grade=grade,
                    board=board,
                    sessions=sessions,
                    studio_ids=selected,
                    studio_names=[studio_names[k] for k in selected],
                    plan_text=plan_text,
                    objectives=objectives,
                    generated_by=teacher_name,
                    created_by=user_email,
                )
                act.log_event(act.EventType.PLAN_GENERATE,
                              entity_id=plan.plan_id, entity_name=plan.display_title(),
                              metadata={"studios": plan.studio_names})
                st.session_state["current_plan"] = plan.model_dump()
                st.session_state["teacher_name"] = teacher_name
            except Exception as e:
                st.error(f"Generation failed: {e}")
                st.info("Check your Anthropic API key in Settings.")
                return

    # ── Show result ───────────────────────────────────────────────────────────
    if "current_plan" in st.session_state:
        _render_plan_result()


def _render_plan_result():
    plan_data = st.session_state["current_plan"]
    plan      = LessonPlan(**plan_data)

    st.divider()
    st.markdown(f"#### {plan.display_title()}")
    studios_str = " + ".join(plan.studio_names)
    st.caption(f"Studios: {studios_str}  ·  {plan.sessions} session(s)  ·  {plan.board}")

    # Learning objectives callout
    if plan.objectives:
        with st.expander("🎯 Learning Objectives", expanded=True):
            for obj in plan.objectives:
                st.markdown(f"- {obj}")

    # Full plan
    st.markdown(plan.plan_text)

    st.divider()

    # Rate and save
    st.markdown("#### Save This Plan")
    c1, c2 = st.columns([1, 2])
    with c1:
        rating = st.feedback("stars", key="plan_rating")
    with c2:
        notes = st.text_input("Notes (optional)",
                               placeholder="e.g. Works well, extend session 2 by 10 mins")

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("💾 Save Plan", type="primary", use_container_width=True):
            user       = st.session_state.get("user", {})
            user_email = user.get("email", "")
            if rating is not None:
                plan.set_rating(user_email, rating + 1, notes)
            plan.saved = True
            storage.save_plan(plan)
            act.log_event(act.EventType.PLAN_SAVE,
                          entity_id=plan.plan_id, entity_name=plan.display_title())
            if rating is not None and (rating + 1) >= 4:
                act.log_event(act.EventType.PLAN_RATE,
                              entity_id=plan.plan_id, entity_name=plan.display_title(),
                              metadata={"stars": rating + 1})
                _update_studio_ratings(plan)
            del st.session_state["current_plan"]
            st.success("✅ Plan saved! Find it in the Explore tab.")
            st.rerun()
    with c2:
        st.download_button(
            "📥 Download",
            data=plan.plan_text,
            file_name=f"{plan.topic.lower().replace(' ', '_')}_grade{plan.grade}.md",
            mime="text/markdown",
            use_container_width=True,
            key="dl_plan"
        )
    with c3:
        if st.button("🔄 Regenerate", use_container_width=True):
            del st.session_state["current_plan"]
            st.rerun()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_all_studios() -> list[tuple[Path, object]]:
    result = []
    for p in storage.list_studios():
        try:
            result.append((p, storage.load_studio(p)))
        except:
            pass
    return result


def _find_similar_plans(subject: str, grade: str) -> list[LessonPlan]:
    """Find saved plans with same subject or grade for context."""
    similar = []
    for p in storage.list_plans():
        try:
            plan = storage.load_plan(p)
            if plan.subject == subject or plan.grade == grade:
                similar.append(plan)
        except:
            pass
    return sorted(similar, key=lambda p: p.average_rating() or 0, reverse=True)[:3]


def _update_studio_ratings(plan: LessonPlan):
    """When a plan is rated 4+, increment use_count on matching coursework."""
    for p in storage.list_studios():
        try:
            profile = storage.load_studio(p)
            if profile.studio_id in plan.studio_ids or p.stem in plan.studio_ids:
                changed = False
                for cw in profile.coursework:
                    if (cw.topic.lower() in plan.topic.lower() or
                            plan.topic.lower() in cw.topic.lower()):
                        cw.use_count += 1
                        changed = True
                if changed:
                    storage.save_studio(profile, p)
        except:
            pass
