#!/bin/sh

uv run alembic upgrade head

# Trust the X-Forwarded-* headers from the TLS-terminating ingress so
# request.url_for() for assets are allowed.
export FORWARDED_ALLOW_IPS="${FORWARDED_ALLOW_IPS:-*}"

uv run fastapi run src/bluecore_api/app/main.py --port 8100 --root-path "/api"
