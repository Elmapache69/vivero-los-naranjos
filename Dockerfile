# ══════════════════════════════════════════════════════════════════
#  Jardín y Vivero Los Naranjos — Dockerfile
#  Multi-stage build: imagen mínima y segura para producción
# ══════════════════════════════════════════════════════════════════

# ── Stage 1: Builder ──────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Instalar dependencias del sistema necesarias para compilar paquetes
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiar e instalar dependencias en un venv aislado
COPY requirements.txt .
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt


# ── Stage 2: Runtime ──────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Metadatos
LABEL maintainer="Vivero Los Naranjos"
LABEL version="2.0.0"

# Dependencias runtime de PostgreSQL
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Usuario no-root para seguridad
RUN groupadd -r vivero && useradd -r -g vivero -s /bin/false vivero

WORKDIR /app

# Copiar el virtualenv del builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copiar código de la aplicación
COPY --chown=vivero:vivero app/ ./app/
COPY --chown=vivero:vivero static/ ./static/
COPY --chown=vivero:vivero alembic/ ./alembic/
COPY --chown=vivero:vivero alembic.ini .

# Variables de entorno
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# Cambiar a usuario no-root
USER vivero

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"

# Comando de inicio
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", "--log-level", "info"]
