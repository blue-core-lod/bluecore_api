#!/bin/sh

uv run alembic --name dev upgrade head

uv run dotenv run fastapi dev src/bluecore_api/app/main.py --port 3000