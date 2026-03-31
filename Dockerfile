FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY src/ ./src/

# Create local data directories used as cache in GCS mode
# and as primary storage in local mode
RUN mkdir -p data/studios data/plans data/uploads data/images

# Cloud Run injects PORT env var (default 8080). Expose both for local use.
EXPOSE 8080 8501

CMD ["sh", "-c", \
    "streamlit run src/app.py \
    --server.port=${PORT:-8501} \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.fileWatcherType=none \
    --browser.gatherUsageStats=false"]
