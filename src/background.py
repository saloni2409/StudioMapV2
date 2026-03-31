import threading
import time
from pathlib import Path
import streamlit as st
import storage
import ai as ai_layer

class ImportState:
    """Shared state for a background import task."""
    def __init__(self, filenames):
        self.filenames = filenames
        self.total_files = len(filenames)
        self.current_index = 0
        self.current_filename = ""
        self.status = "idle"  # idle, running, completed, error
        self.progress = 0.0
        self.results = []  # list of (name, path)
        self.errors = []   # list of (filename, error_msg)
        self.start_time = 0.0
        self.end_time = 0.0

    def start(self):
        self.status = "running"
        self.start_time = time.time()

    def update_progress(self, index, filename):
        self.current_index = index
        self.current_filename = filename
        self.progress = (index) / self.total_files

    def finish(self):
        self.status = "completed"
        self.progress = 1.0
        self.end_time = time.time()

    def fail(self, error):
        self.status = "error"
        self.errors.append(("GLOBAL", str(error)))
        self.end_time = time.time()

def start_import(uploaded_files):
    """Start a background import thread."""
    if "import_state" in st.session_state and st.session_state.import_state.status == "running":
        return # Already running
    
    # Store file bytes in memory for the thread (Streamlit's UploadedFile is not thread-safe)
    file_data = []
    filenames = []
    for f in uploaded_files:
        filenames.append(f.name)
        f.seek(0)
        file_data.append((f.name, f.read()))
        
    state = ImportState(filenames)
    st.session_state.import_state = state
    
    thread = threading.Thread(target=_import_worker, args=(file_data, state))
    thread.start()
    state.start()

def _import_worker(file_data, state):
    """The background worker thread."""
    try:
        for i, (name, content) in enumerate(file_data):
            state.update_progress(i + 1, name)
            try:
                profiles = ai_layer.pdf_to_profiles(content)
                for profile in profiles:
                    profile.source_pdf = name
                    path = storage.save_studio(profile)
                    state.results.append((profile.name, path))
            except Exception as e:
                state.errors.append((name, str(e)))
        
        state.finish()
    except Exception as e:
        state.fail(e)

def get_active_import():
    """Get the current import state if any."""
    return st.session_state.get("import_state")

def clear_import():
    """Clear the import state."""
    if "import_state" in st.session_state:
        del st.session_state.import_state
