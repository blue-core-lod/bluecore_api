FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates git

USER airflow
WORKDIR /bluecore_api
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

COPY --chown=airflow:root src ./src
COPY --chown=airflow:root pyproject.toml uv.lock README.md alembic.ini start.sh ./

RUN uv sync && uv build && uv pip install dist/*.whl

CMD ["./start.sh"]
