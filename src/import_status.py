import streamlit as st
import time
from background import get_active_import, clear_import

def render():
    """Render the detailed import status view."""
    state = get_active_import()
    if not state:
        st.info("No active or recent imports found.")
        if st.button("Back to Studios"):
            st.session_state["active_page"] = "studios"
            st.rerun()
        return

    st.markdown("## 📄 Import Status")
    
    # Header stats
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Total Files", state.total_files)
    with c2:
        st.metric("Processed", state.current_index)
    with c3:
        st.metric("Successful Studios", len(state.results))

    # Progress bar
    status_text = f"Status: {state.status.title()}"
    if state.status == "running":
        status_text += f" (Processing {state.current_filename}...)"
    
    st.progress(state.progress, text=status_text)

    # Tabs for details
    t1, t2 = st.tabs(["✅ Successes", "❌ Errors & Logs"])
    
    with t1:
        if not state.results:
            st.caption("No studios imported yet.")
        else:
            for name, path in state.results:
                st.success(f"**{name}** imported successfully.")
                if st.button(f"Edit {name}", key=f"edit_res_{path.stem}"):
                    st.session_state["active_page"] = "studios"
                    st.session_state["studio_mode"] = "edit"
                    st.session_state["studio_path"] = str(path)
                    st.rerun()

    with t2:
        if not state.errors:
            st.caption("No errors encountered.")
        else:
            for filename, error in state.errors:
                st.error(f"**{filename}**: {error}")

    st.divider()
    
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Back to Studios", use_container_width=True):
            st.session_state["active_page"] = "studios"
            st.rerun()
    with c2:
        if state.status != "running":
            if st.button("Clear and Dismiss", type="primary", use_container_width=True):
                clear_import()
                st.session_state["active_page"] = "studios"
                st.rerun()
        else:
            if st.button("🔄 Refresh", use_container_width=True):
                st.rerun()

    # Auto-refresh if running
    if state.status == "running":
        time.sleep(2)
        st.rerun()
