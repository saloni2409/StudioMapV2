"""
StudioMap — Settings
=====================
API keys, storage mode, Google Drive config, backup.
Lives in the sidebar as a persistent ⚙️ button.
"""

import streamlit as st
import storage
import ai as ai_layer
import auth
import activity as act
from config import CREDS_FILE, load_config, save_config, now_str, ALL_SUBJECTS


def render():
    st.markdown("## ⚙️ Settings")
    cfg     = load_config()
    changed = False

    # ── School ────────────────────────────────────────────────────────────────
    st.markdown("#### 🏫 School")
    v  = cfg.get("school_name", "")
    nv = st.text_input("School Name", value=v, placeholder="e.g. The Meadows School")
    if nv != v:
        cfg["school_name"] = nv; changed = True

    st.divider()

    # ── Subjects List ─────────────────────────────────────────────────────────
    st.markdown("#### 📚 Subjects List")
    st.caption("Custom subjects are available across studio and plan forms. Built-in subjects cannot be removed.")

    custom = cfg.get("custom_subjects", [])
    if custom:
        for subj in custom:
            sc1, sc2 = st.columns([5, 1])
            sc1.write(subj)
            if sc2.button("Remove", key=f"rm_subj_{subj}"):
                cfg["custom_subjects"] = [s for s in custom if s != subj]
                save_config(cfg)
                st.rerun()
    else:
        st.caption("No custom subjects added yet.")

    new_subj = st.text_input("Add a new subject", placeholder="e.g. Foreign Languages, Drama, Music")
    if st.button("➕ Add Subject") and new_subj.strip():
        subj = new_subj.strip()
        if subj in ALL_SUBJECTS:
            st.info(f'"{subj}" is already in the built-in list.')
        elif subj in custom:
            st.info(f'"{subj}" is already in your custom list.')
        else:
            cfg["custom_subjects"] = custom + [subj]
            save_config(cfg)
            st.rerun()

    st.divider()

    # ── AI Configuration ──────────────────────────────────────────────────────
    st.markdown("#### 🧠 AI Configuration")
    st.caption("Required for PDF import and lesson plan generation.")
    
    current_provider = cfg.get("ai_provider", "anthropic")
    
    # Provider Selection
    provider_options = ["anthropic", "openai", "local"]
    provider_labels = ["Claude (Anthropic)", "ChatGPT (OpenAI)", "Local Model (Ollama/LMStudio)"]
    
    sel_idx = provider_options.index(current_provider) if current_provider in provider_options else 0
    new_provider_label = st.radio("AI Provider", provider_labels, index=sel_idx)
    new_provider = provider_options[provider_labels.index(new_provider_label)]
    
    if new_provider != current_provider:
        cfg["ai_provider"] = new_provider; changed = True
        
    st.write("") # Spacer

    # Conditional inputs based on selected provider
    if new_provider == "anthropic":
        v  = cfg.get("anthropic_api_key", "")
        nv = st.text_input("Anthropic API Key", value=v, type="password", placeholder="sk-ant-...")
        if nv != v: cfg["anthropic_api_key"] = nv; changed = True

    elif new_provider == "openai":
        v  = cfg.get("openai_api_key", "")
        nv = st.text_input("OpenAI API Key", value=v, type="password", placeholder="sk-proj-...")
        if nv != v: cfg["openai_api_key"] = nv; changed = True

    elif new_provider == "local":
        c1, c2 = st.columns(2)
        with c1:
            v_url  = cfg.get("local_model_url", "http://127.0.0.1:11434/v1")
            nv_url = st.text_input("Base URL", value=v_url, placeholder="http://127.0.0.1:11434/v1")
            if nv_url != v_url: cfg["local_model_url"] = nv_url; changed = True
        with c2:
            v_mod  = cfg.get("local_model_name", "llama3")
            nv_mod = st.text_input("Model Name", value=v_mod, placeholder="llama3")
            if nv_mod != v_mod: cfg["local_model_name"] = nv_mod; changed = True

    st.write("") # Spacer
    if st.button("🔌 Test Connection"):
        # Save before testing so the AI layer reads the correct unsaved inputs
        save_config(cfg)
        with st.spinner(f"Testing {new_provider_label}..."):
            ok, msg = ai_layer.check_api_key()
        st.success(msg) if ok else st.error(msg)

    st.divider()

    # ── Storage Mode ──────────────────────────────────────────────────────────
    st.markdown("#### 💾 Storage")
    mode = cfg.get("storage_mode", "local")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("💾 Local", use_container_width=True,
                      type="primary" if mode == "local" else "secondary"):
            cfg["storage_mode"] = "local"; save_config(cfg)
            st.success("Switched to Local"); st.rerun()
    with c2:
        if st.button("☁️ Google Drive", use_container_width=True,
                      type="primary" if mode == "drive" else "secondary"):
            cfg["storage_mode"] = "drive"; save_config(cfg)
            st.success("Switched to Drive"); st.rerun()

    if mode == "local":
        st.info("Files saved to `data/` folder on this machine.")
    else:
        st.info("Files synced to Google Drive.")

    st.divider()

    # ── Google Drive ──────────────────────────────────────────────────────────
    st.markdown("#### ☁️ Google Drive")

    with st.expander("Setup Guide"):
        st.markdown("""
1. [console.cloud.google.com](https://console.cloud.google.com) → New project
2. Enable **Google Drive API**
3. **IAM → Service Accounts → Create** → download JSON key
4. Save the JSON as **credentials.json** next to app.py
5. In Google Drive, create a folder → Share with service account email (Editor)
6. Copy the folder ID from the Drive URL → paste below
        """)

    # Credentials file
    if CREDS_FILE.exists():
        st.success(f"✅ credentials.json found")
    else:
        st.warning("⚠️ credentials.json not found")
        up = st.file_uploader("Upload credentials.json", type=["json"],
                               key="creds_upload")
        if up:
            CREDS_FILE.write_bytes(up.getbuffer())
            st.success("✅ Saved!"); st.rerun()

    v  = cfg.get("drive_folder_id", "")
    nv = st.text_input("Data Folder ID", value=v,
                        placeholder="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs")
    if nv != v: cfg["drive_folder_id"] = nv; changed = True

    v  = cfg.get("drive_backup_folder_id", "")
    nv = st.text_input("Backup Folder ID (optional)", value=v,
                        placeholder="Leave blank to use same folder")
    if nv != v: cfg["drive_backup_folder_id"] = nv; changed = True

    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔌 Test Drive", use_container_width=True):
            with st.spinner("Connecting..."):
                ok, msg = storage.test_drive()
            st.success(msg) if ok else st.error(msg)
    with c2:
        if st.button("🔄 Sync Local → Drive", use_container_width=True):
            with st.spinner("Syncing..."):
                ok, msg, n = storage.sync_to_drive()
            st.success(msg) if ok else st.error(msg)

    st.divider()

    # ── Backup ────────────────────────────────────────────────────────────────
    st.markdown("#### 🗄️ Backup")

    c1, c2 = st.columns(2)
    with c1:
        st.caption(f"Last download: {cfg.get('last_backup_local') or 'Never'}")
        if st.button("📦 Prepare Download", use_container_width=True):
            with st.spinner("Creating ZIP..."):
                zb, zn = storage.create_backup_zip()
            st.session_state["bzip"] = zb
            st.session_state["bzip_name"] = zn
            st.success(f"Ready ({len(zb)//1024} KB)")

        if "bzip" in st.session_state:
            if st.download_button("⬇️ Download ZIP",
                                   data=st.session_state["bzip"],
                                   file_name=st.session_state["bzip_name"],
                                   mime="application/zip",
                                   use_container_width=True):
                cfg["last_backup_local"] = now_str()
                save_config(cfg)

    with c2:
        st.caption(f"Last Drive backup: {cfg.get('last_backup_drive') or 'Never'}")
        drive_ready = bool(cfg.get("drive_folder_id") and CREDS_FILE.exists())
        if not drive_ready:
            st.warning("Configure Drive above first.")
        else:
            if st.button("☁️ Backup to Drive", type="primary",
                          use_container_width=True):
                with st.spinner("Uploading..."):
                    ok, msg = storage.backup_to_drive()
                st.success(msg) if ok else st.error(msg)
                if ok: st.rerun()

    st.divider()

    # ── Google OAuth ──────────────────────────────────────────────────────────
    st.markdown("#### 🔐 Google OAuth")
    st.caption("Required for user login. Set up at console.cloud.google.com → APIs & Services → Credentials.")

    with st.expander("OAuth Setup Guide"):
        st.markdown("""
1. Go to [Google Cloud Console](https://console.cloud.google.com) → **APIs & Services → Credentials**
2. Click **Create Credentials → OAuth 2.0 Client ID** → Application type: **Web application**
3. Add your Cloud Run URL + `/` to **Authorised redirect URIs** (e.g. `https://your-app.run.app/`)
4. Copy **Client ID** and **Client Secret** below
5. Set `ADMIN_EMAIL` to your Google account email
        """)

    v  = cfg.get("google_client_id", "")
    nv = st.text_input("Google Client ID", value=v, placeholder="123...apps.googleusercontent.com")
    if nv != v: cfg["google_client_id"] = nv; changed = True

    v  = cfg.get("google_client_secret", "")
    nv = st.text_input("Google Client Secret", value=v, type="password", placeholder="GOCSPX-...")
    if nv != v: cfg["google_client_secret"] = nv; changed = True

    v  = cfg.get("google_redirect_uri", "http://localhost:8501")
    nv = st.text_input("Redirect URI", value=v, placeholder="https://your-app.run.app/")
    if nv != v: cfg["google_redirect_uri"] = nv; changed = True

    v  = cfg.get("admin_email", "")
    nv = st.text_input("Admin Email", value=v, placeholder="admin@yourschool.org")
    if nv != v: cfg["admin_email"] = nv; changed = True

    v  = cfg.get("google_workspace_domain", "")
    nv = st.text_input("Workspace Domain (optional)", value=v,
                        placeholder="yourschool.org — leave blank to allow any Google account")
    if nv != v: cfg["google_workspace_domain"] = nv; changed = True

    st.divider()

    # ── Activity Log ──────────────────────────────────────────────────────────
    st.markdown("#### 📊 Activity Log")
    _is_admin = auth.is_admin(cfg)

    with st.expander("View Activity"):
        import pandas as pd
        from datetime import date, timedelta

        c1, c2 = st.columns(2)
        with c1:
            start = st.date_input("From", value=date.today() - timedelta(days=7))
        with c2:
            end = st.date_input("To", value=date.today())

        start_str = start.strftime("%Y-%m-%d")
        end_str   = end.strftime("%Y-%m-%d")

        if _is_admin:
            events = storage.list_all_activity(start_str, end_str)
        else:
            user = st.session_state.get("user", {})
            events = storage.list_activity(user.get("email", ""), start_str, end_str)

        if events:
            rows = [{
                "Time":   e.timestamp[:16].replace("T", " "),
                "User":   e.user_email,
                "Action": e.event_type.value,
                "Item":   e.entity_name,
            } for e in events]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("No activity in this date range.")

    st.divider()

    # ── Save ──────────────────────────────────────────────────────────────────
    if changed:
        st.warning("Unsaved changes")
    if st.button("💾 Save Settings", type="primary", use_container_width=True):
        save_config(cfg)
        act.log_event(act.EventType.SETTINGS_SAVE)
        st.success("✅ Saved!")
        st.rerun()
