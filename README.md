# Blue Core API

API for managing Blue Core resources and workflows using PostgreSQL and Airflow platforms.


## 🗂️ Project structure
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

---

## 🛠️ Installation

### 🧰 Prerequisites
- [uv](https://github.com/astral-sh/uv)
- [Docker](https://www.docker.com/)
- [Blue Core Data Models][BLUECORE_MODELS]
 
### 🔧 Installation instructions
1.  Run `uv pip install -r requirements.txt`, and follow the instructions that appear.
2.  Run `docker-compose pull` to pull down all images.
3.  Clone the [Blue Core Data Models][BLUECORE_MODELS] repository to run the Alembic
    database migrations.

---

## 🚀 Running the application
To start all of the supporting services (PostgreSQL, etc.):
`docker-compose up -d`

The Postgres Docker database will be available on port 5432. When the database is first brought up, 
the `create-db.sql` script is run that creates a `bluecore` database with a 
`bluecore_admin` user. 

After the database is up, change directories to the cloned [Blue Core Data Models][BLUECORE_MODELS] and then from that directory run `uv run alembic upgrade head`
to create the latest database tables and indices for the database.

**🛠️ In development (Non Dockerized)**: To start the FastAPI rest server in dev mode:
> ⚠️ Note: This method only runs the api server and not the supporting services in docker (keycloak, nginx, etc.)
> [Recommended: Run with Docker](#running-locally-with-docker)

1. Run `export DATABASE_URL=postgresql://bluecore_admin:bluecore_admin@localhost/bluecore` to add the needed environmental variable 
2. Run the application at *http://localhost:3000*
`uv run fastapi dev src/bluecore/app/main.py --port 3000`
3. Look at the API docs at *https://localhost:3000/docs/*

This is in development mode and code changes will immediately be loaded without having to restart the server.

---

## 👨‍💻 Developers
### 🐳 Running Locally with Docker
Dev Docker compose file needs to be specified when starting the container service.

```bash
docker compose -f compose-dev.yaml up
```
### 🚧 Accessing App
Local development URL:
>  - http://localhost



### 🔐 Bypassing Keycloak 
To access the API without needing the API to authenticate with Keycloak: 
* Uncomment `BYPASS_KEYCLOAK: "true"` in `compose-dev.yaml`

### 🔑 Logging into Keycloak master realm
You can also create a new realm and client in Keycloak by going to:
> - http://localhost/keycloak 
> - username: `admin` 
> - password: `gracious-professed`

### 🧹 Linter for Python 
Bluecore API uses [ruff](https://docs.astral.sh/ruff/)
- `uv run ruff check`

To auto-fix errors in both (where possible):
- `uv run ruff check --fix`

Check formatting differences without changing files:
- `uv run ruff format --diff`

Apply Ruff's code formatting:
- `uv run ruff format`


💡 It's a good idea to run both check and format to catch lint and formatting issues. 
Github Actions will fail if either check or format fails.

### 🧪 Unit, feature, and integration tests
The test suite is written using pytest and is executed via uv.
All tests are located in the `tests/` directory.

To run all of the tests:
- `uv run pytest`

To drop into the Python debugger when a test fails add the following parameters to above command:
- `uv run pytest -s --pdb` 


[BLUECORE_MODELS]: https://github.com/blue-core-lod/bluecore-models
