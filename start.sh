#!/bin/sh

uv run alembic upgrade head

uv run fastapi run src/bluecore_api/app/main.py --port 8100 --root-path "/api"
