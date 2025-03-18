import pytest

import pathlib
import os
import sys
from pytest_mock_resources import PostgresConfig

if os.getenv("DATABASE_URL") is None:
    os.environ["DATABASE_URL"] = (
        "postgresql://bluecore_admin:bluecore_admin@localhost/bluecore"
    )


@pytest.fixture(scope="session")
def pmr_postgres_config():
    return PostgresConfig(image="pgvector/pgvector:pg17")


root_directory = pathlib.Path(__file__).parent.parent
dir = root_directory / "src/"

sys.path.append(str(dir))
