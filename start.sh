#!/bin/sh

uv run alembic upgrade head

# Trust X-Forwarded-* from the reverse proxy
uv run fastapi run src/bluecore_api/app/main.py --port 8100 --root-path "/api" --forwarded-allow-ips "*"
