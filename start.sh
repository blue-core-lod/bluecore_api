#!/bin/sh

alembic upgrade head

# Trust X-Forwarded-* from the reverse proxy
fastapi run src/bluecore_api/app/main.py --port 8100 --root-path "/api" --forwarded-allow-ips "*"
