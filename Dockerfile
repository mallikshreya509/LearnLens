# One container serves the API and the frontend (see backend/app/main.py).
# Build context is the repo root, so backend/ and frontend/ sit side by side as they do locally.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first, so code changes do not reinstall them.
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

COPY backend/app backend/app
COPY backend/samples backend/samples
COPY frontend frontend

RUN useradd --create-home --uid 10001 app
USER app

WORKDIR /app/backend

# Cloud Run sets PORT (8080 by default). `exec` lets uvicorn receive SIGTERM and shut down cleanly.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
