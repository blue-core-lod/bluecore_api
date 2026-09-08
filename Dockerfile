# ---- builder: resolve deps and install the project into a self-contained venv ----
FROM python:3.12-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /build
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
# --no-editable so the venv doesn't depend on /build existing at runtime
RUN uv sync --frozen --no-dev --no-editable

# ---- runtime: plain python + the built venv, no uv/build tooling ----
FROM python:3.12-slim-bookworm AS runtime
ARG AIRFLOW_UID="50000"
ARG AIRFLOW_USER_HOME_DIR=/home/airflow

ENV AIRFLOW_UID=${AIRFLOW_UID} \
    AIRFLOW_USER_HOME_DIR=${AIRFLOW_USER_HOME_DIR} \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN adduser --quiet "airflow" --uid "${AIRFLOW_UID}" --gid "0" \
    --home "${AIRFLOW_USER_HOME_DIR}" && \
    mkdir -p /bluecore_api && chown -R airflow:0 /bluecore_api && chmod -R g=u /bluecore_api

WORKDIR /bluecore_api
COPY --from=builder --chown=airflow:0 /opt/venv /opt/venv
# src is still needed at runtime: start.sh runs fastapi against this file path
COPY --chown=airflow:0 src ./src
COPY --chown=airflow:0 alembic.ini start.sh ./
RUN chmod -R g=u /bluecore_api

USER airflow
CMD ["./start.sh"]
