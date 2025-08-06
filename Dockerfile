FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates git

ADD https://astral.sh/uv/install.sh /uv-installer.sh

RUN sh /uv-installer.sh && rm /uv-installer.sh

ENV PATH="/root/.local/bin/:$PATH"

WORKDIR /bluecore_api

COPY src src
ADD pyproject.toml .
ADD uv.lock .
ADD README.md .

RUN uv sync
RUN uv build
RUN uv pip install --system dist/*.whl

CMD ["uv", "run", "uvicorn", "src.bluecore_api.app.main:base_app", "--host", "0.0.0.0", "--port", "8100", "--root-path", "/api", "--proxy-headers", "--forwarded-allow-ips", "*"]