FROM python:3.12-slim-bookworm
ARG AIRFLOW_UID="50000"
ARG AIRFLOW_GID="50000"
ARG AIRFLOW_USER_HOME_DIR=/home/airflow

ENV AIRFLOW_UID=${AIRFLOW_UID} \
    AIRFLOW_GID=${AIRFLOW_GID} \
    AIRFLOW_USER_HOME_DIR=${AIRFLOW_USER_HOME_DIR} \
    PATH="/home/airflow/.local/bin/:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates git && \
    addgroup --gid "${AIRFLOW_GID}" "airflow" && \
    adduser --quiet "airflow" --uid "${AIRFLOW_UID}" \
    --gid "${AIRFLOW_GID}" \
    --home "${AIRFLOW_USER_HOME_DIR}"

USER airflow
WORKDIR /bluecore_api
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

COPY --chown=airflow:root src ./src
COPY --chown=airflow:root pyproject.toml uv.lock README.md ./

ENV UV_CACHE_DIR=${AIRFLOW_USER_HOME_DIR}/.cache/uv
RUN mkdir -p ${UV_CACHE_DIR} && uv sync && uv build && uv pip install dist/*.whl

CMD ["uv", "run", "fastapi", "run", "src/bluecore_api/app/main.py", "--port", "8100", "--root-path", "/api"]
