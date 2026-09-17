# Container image for the Q&A assistant. Used by Render (render.yaml) and runs
# the same way on any machine with Docker.

FROM python:3.12-slim

# PYTHONUNBUFFERED so logs appear in the host's log viewer straight away
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

# requirements first: this layer is cached and only rebuilds when the
# dependency list changes, not on every code edit
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as a normal user, not root. The uploads folder is the only path the app
# writes to, so it is the only one that needs to be owned by that user.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data/uploads \
    && chown -R appuser:appuser /app/data
USER appuser

EXPOSE 8000

# The host (Render) injects its own PORT; the default covers running locally.
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
