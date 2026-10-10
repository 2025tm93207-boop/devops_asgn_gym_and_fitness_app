# syntax=docker/dockerfile:1

# ---------- base: shared settings ----------
FROM python:3.12-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Unprivileged user to run the app
RUN groupadd --system app && \
    useradd --system --gid app --home-dir /app --no-create-home app

# ---------- builder: install runtime dependencies into a venv ----------
FROM base AS builder

COPY requirements.txt .
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install -r requirements.txt

# ---------- app: application code on top of the venv ----------
FROM base AS app

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    DATABASE=/app/instance/aceest_fitness.db

COPY app.py .
COPY aceest/ aceest/
RUN mkdir -p /app/instance && chown app:app /app/instance

# ---------- test: app + pytest, used by CI (docker build --target test) ----------
FROM app AS test

COPY requirements.txt requirements-dev.txt ./
RUN pip install -r requirements-dev.txt
COPY pytest.ini .
COPY tests/ tests/

USER app
CMD ["pytest", "-v", "-p", "no:cacheprovider"]

# ---------- runtime: final production image (default target) ----------
FROM app AS runtime

USER app
EXPOSE 5000
VOLUME ["/app/instance"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health', timeout=3)"]

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--preload", \
     "--access-logfile", "-", "app:app"]
