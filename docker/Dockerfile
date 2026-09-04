# Paśnik — obraz aplikacji.
#
# Multi-stage. W BATCH_01 istnieje wyłącznie ścieżka deweloperska:
#   base → dev   (uvicorn --reload, kod z bind mounta)
# Target `prod` (build SPA + StaticFiles wg ADR-014) dokłada BATCH_17 —
# świadomie nie tworzymy nieprzetestowanego stage'a „na zapas".
#
# Budowanie zawsze z korzenia repo:
#   docker build -f docker/Dockerfile --target dev .

# --- base: zależności backendu ---------------------------------------------
FROM python:3.13-slim AS base

# uv jako package manager (01_ARCHITECTURE §3).
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /usr/local/bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    # Venv POZA /app: katalog /app jest w dev nadpisywany bind mountem
    # z hosta (Windows), a venv hosta nie działa w kontenerze Linux.
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/opt/venv/bin:${PATH}"

WORKDIR /app

# Warstwa zależności osobno od kodu — przebudowa tylko przy zmianie locka.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-install-project

# --- dev: hot reload, kod z bind mounta ------------------------------------
FROM base AS dev

# Narzędzia diagnostyczne przydatne w pętli dev (healthcheck, debug bazy).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Dev-owe zależności (pytest, ruff, mypy) — w obrazie prod ich nie będzie.
RUN uv sync --frozen --no-install-project --group dev

EXPOSE 8000

# --reload-dir app: bez tego watchfiles skanuje cały bind mount (wolne na
# Windows/WSL2). WATCHFILES_FORCE_POLLING ustawia compose.
CMD ["uvicorn", "app.main:create_app", "--factory", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--reload", "--reload-dir", "app"]
