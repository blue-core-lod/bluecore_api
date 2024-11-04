# Blue Core API

API for managing Blue Core resources and workflows using PostgresSQL and Airflow platforms.


## Project structure
```
src/bluecore_api/
│
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── resource.py
│   │   ├── user.py
│   │   └── metrics.py
│   │
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── resource.py
│   │   ├── user.py
│   │   └── metrics.py
│   │
│   └── routers/
│       ├── __init__.py
│       ├── resources.py
│       ├── users.py
│       └── metrics.py
│
├── pyproject.yaml
└── README.md
```



## Installation

### Prerequisites
- [uv](https://github.com/astral-sh/uv)
- [Docker](https://www.docker.com/)
 
### Installation instructions
1.  Run `uv pip install -r requirements.txt`, and follow the instructions that appear.
2.  Run `docker-compose pull` to pull down all images.

## Running the application
To start all of the supporting services (PostgresSQL, etc.):
`docker-compose up -d`

To start the FastAPI rest server in dev mode and run the application at [http://localhost:3000](http://localhost:3000):
`uv run fastapi dev src/bluecore/app/main.py --port 3000`

This is in development mode and code changes will immediately be loaded without having to restart the server.



## Developers


### Frameworks

### Linter for Python 
Bluecore API uses [ruff].

`uv run ruff check`

To auto-fix errors in both (where possible):
`uv run ruff check --fix`

### Unit, feature, and integration tests

Tests are written with pytest.

To run all of the tests:
`uv run pytest tests/`

#### Dev/Stage/Prod

#### Issuing queries

### Get a JWT

TBD

#### Use JWT in HTTP Request

TBD
