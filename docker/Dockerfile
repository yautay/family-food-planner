# Paśnik — obraz aplikacji.
#
# Multi-stage:
#   base           → zależności backendu w /opt/venv (uv)
#   dev            → base + grupa dev, uvicorn --reload, kod z bind mounta
#   frontend-build → node:22, `vite build` → /build/dist
#   prod           → base bez dev-deps + kod + dist (ADR-014), USER nie-root,
#                    2 workery uvicorna, --proxy-headers (za Caddym, D7)
#
# Budowanie zawsze z korzenia repo:
#   docker build -f docker/Dockerfile --target dev .
#   task build-prod   # = --target prod, tag pasnik-app:<git describe>
#
# UID/GID 10001 jest WSPÓLNY z obrazem backupu (docker/backup/Dockerfile):
# oba kontenery czytają/piszą ten sam wolumen uploadów, więc muszą być tym
# samym użytkownikiem systemowym (09_DEPLOYMENT §1 — bind mounty na hoście
# dostają `chown 10001:10001`).

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
# `--no-dev`: grupa `dev` (pytest, ruff, mypy) jest w uv grupą DOMYŚLNĄ — bez
# tej flagi wchodziłaby do warstwy `base`, a usunięcie jej w `prod` nie odchudza
# obrazu (warstwy nakładają się, nie kasują). Stage `dev` dokłada ją jawnie.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# --- dev: hot reload, kod z bind mounta ------------------------------------
FROM base AS dev

# Narzędzia diagnostyczne przydatne w pętli dev (healthcheck, debug bazy).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Dev-owe zależności (pytest, ruff, mypy) — tylko tutaj, nigdy w `base`/`prod`.
RUN uv sync --frozen --no-install-project --group dev

EXPOSE 8000

# --reload-dir app: bez tego watchfiles skanuje cały bind mount (wolne na
# Windows/WSL2). WATCHFILES_FORCE_POLLING ustawia compose.
CMD ["uvicorn", "app.main:create_app", "--factory", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--reload", "--reload-dir", "app"]

# --- frontend-build: SPA do obrazu prod (ADR-014) ---------------------------
FROM node:22-alpine AS frontend-build

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# To samo polecenie co `task fe-build` (bramka) — typy sprawdza `task check`.
RUN npx vite build

# --- prod: bez dev-deps, dist w obrazie, nie-root ---------------------------
FROM base AS prod

# Wersja obrazu = tag gita (`task build-prod`), spójna z polem `version` health.
ARG APP_VERSION=0.0.0-dev
ENV APP_VERSION=${APP_VERSION} \
    APP_ENV=prod \
    SPA_DIST_DIR=/app/static \
    UPLOADS_DIR=/data/uploads

RUN groupadd --system --gid 10001 pasnik \
    && useradd --system --uid 10001 --gid pasnik --home /app --shell /usr/sbin/nologin pasnik \
    && mkdir -p /data/uploads \
    && chown -R pasnik:pasnik /data

# Kod bez testów, bez .env, bez danych (patrz .dockerignore w korzeniu repo).
COPY --chown=pasnik:pasnik backend/app ./app
COPY --chown=pasnik:pasnik backend/migrations ./migrations
COPY --chown=pasnik:pasnik backend/alembic.ini ./alembic.ini
COPY --chown=pasnik:pasnik backend/scripts ./scripts
COPY --chown=pasnik:pasnik --from=frontend-build /build/dist ./static
COPY --chmod=755 docker/entrypoint.sh /usr/local/bin/pasnik-entrypoint

USER pasnik
EXPOSE 8000

# Healthcheck obrazu: SAM KOD HTTP. `degraded` też jest 200 (09_DEPLOYMENT §2) —
# kontener, który odpowiada, nie ma być restartowany w pętli za niezmigrowaną
# bazę; treść statusu czyta operator (`docker compose exec app python -c ...`
# albo `curl`). Compose może nadpisać interwały.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4).status == 200 else 1)"]

CMD ["pasnik-entrypoint"]
