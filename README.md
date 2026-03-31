# 🏫 StudioMap v2

StudioMap is an AI-powered knowledge base and lesson plan generator designed for experiential learning schools. It helps teachers document their physical studio spaces and generate lesson plans that genuinely leverage the unique tools and affordances of those spaces.

## ✨ Key Features
- **Smart PDF Ingestion**: Upload studio documentation PDFs. The AI automatically extracts studio names, descriptions, tools, and teaching ideas.
- **Multi-Studio Detection**: Now supports detecting and extracting multiple distinct studios from a single PDF document.
- **Lesson Plan Generator**: Research-backed lesson plans grounded in your actual school environment.
- **Curriculum Map**: A searchable "Explore" tab to see how studios are being used across subjects and grades.

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.8 or higher
- An API Key from **Anthropic** (Claude), **OpenAI** (ChatGPT), or a local LLM setup.

### 2. Installation
Clone the repository and install the dependencies:
```bash
# Recommended: Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install requirements
pip install -r requirements.txt
```

### 3. Running the App
The application is built with Streamlit. To start it, run:
```bash
streamlit run src/app.py
```

### 4. Configuration
Once the app is running, navigate to the **⚙️ Settings** tab to:
- Enter your AI Provider API Keys.
- Switch between Local and Google Drive storage modes.
- Set your school name.

## 💡 Tips

### Cleaner Directories
If you want to keep your project folders clean of `__pycache__` files, you can redirect them to a central location by adding this to your shell profile (`.zshrc` or `.bash_profile`):
```bash
export PYTHONPYCACHEPREFIX="$HOME/.cache/pycache"
```

## 🛠️ Testing
To run the automated verification tests for the AI layer:
```bash
export PYTHONPATH=$PYTHONPATH:$(pwd)/src 
python3 tests/verify_multi_studio.py
```
