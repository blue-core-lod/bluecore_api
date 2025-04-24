# Blue Core API

API for managing Blue Core resources and workflows using PostgreSQL and Airflow platforms.


## Project structure
```
bluecore_store_migrations/
|  |── env.py
|  |── versions/
|
src/bluecore_api/
│   │
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── config.py
│   │   
│   │  
│   └── models.py
tests/
|
├── pyproject.yaml
└── README.md
```


## Installation

### Prerequisites
- [uv](https://github.com/astral-sh/uv)
- [Docker](https://www.docker.com/)
- [Blue Core Data Models][BLUECORE_MODELS]
 
### Installation instructions
1.  Run `uv pip install -r requirements.txt`, and follow the instructions that appear.
2.  Run `docker-compose pull` to pull down all images.
3.  Clone the [Blue Core Data Models][BLUECORE_MODELS] repository to run the Alembic
    database migrations.

## Running the application
To start all of the supporting services (PostgreSQL, etc.):
`docker-compose up -d`

The Postgres Docker database will be available on port 5432. When the database is first brought up, 
the `create-db.sql` script is run that creates a `bluecore` database with a 
`bluecore_admin` user. 

After the database is up, change directories to the cloned [Blue Core Data Models][BLUECORE_MODELS] and then from that directory run `uv run alembic upgrade head`
to create the latest database tables and indices for the database.


**In development**: To start the FastAPI rest server in dev mode:
1. Run `export DATABASE_URL=postgresql://bluecore_admin:bluecore_admin@localhost/bluecore` to add the needed environmental variable 
2. Run the application at *http://localhost:3000*
`uv run fastapi dev src/bluecore/app/main.py --port 3000`
3. Look at the API docs at *https://localhost:3000/docs/*

This is in development mode and code changes will immediately be loaded without having to restart the server.

## Developers

### 🔐 Bypassing Keycloak 
To access the API without needing to authenticate with Keycloak: 
* run `export DEVELOPER_MODE=true` before running the application. 

### Linter for Python 
Bluecore API uses [ruff](https://docs.astral.sh/ruff/)
- `uv run ruff check`

To auto-fix errors in both (where possible):
- `uv run ruff check --fix`

### Unit, feature, and integration tests
Unit and Feature Tests are written with pytest.

To run all of the tests:
- `uv run pytest`

To drop into the Python debugger when a test fails add the following parameters to above command:
- `uv run pytest -s --pdb` 


[BLUECORE_MODELS]: https://github.com/blue-core-lod/bluecore-models
