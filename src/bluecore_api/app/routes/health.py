from importlib.metadata import version

from fastapi import APIRouter

from bluecore_api.schemas.schemas import HealthSchema

endpoints = APIRouter()

# Read once at import: the distribution metadata is written from pyproject.toml
# at build/install time and can't change while the process is running.
API_VERSION = version("bluecore-api")


@endpoints.get("/health", operation_id="health", response_model=HealthSchema)
async def health() -> HealthSchema:
    """Report that the API is up, along with the running version."""
    return HealthSchema(status="ok", version=API_VERSION)
