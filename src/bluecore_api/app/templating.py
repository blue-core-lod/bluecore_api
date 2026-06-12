"""Shared Jinja2 templating setup for the HTML views.

Templates reference absolute URLs built from:
`TEMPLATES_DIR` `BLUECORE_URL`, `MARVA_BASE_URL`, `SINOPIA_BASE_URL`.
These values are exposed as Jinja globals so every template can use them.
"""

import os

from fastapi.templating import Jinja2Templates

BLUECORE_URL = os.environ.get("BLUECORE_URL", "https://bcld.info/")
MARVA_BASE_URL = os.environ.get("MARVA_BASE_URL", "https://dev.bcld.info/marva/")
SINOPIA_BASE_URL = os.environ.get("SINOPIA_BASE_URL", "https://dev.bcld.info/sinopia/")

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")

templates = Jinja2Templates(directory=TEMPLATES_DIR)
templates.env.globals["BLUECORE_URL"] = BLUECORE_URL
templates.env.globals["MARVA_BASE_URL"] = MARVA_BASE_URL
templates.env.globals["SINOPIA_BASE_URL"] = SINOPIA_BASE_URL
