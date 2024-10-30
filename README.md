# Blue Core API

API for managing Blue Core resources and workflows using PostgresSQL and Airflow platforms.


## Project structure
```
src/bluecore/
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
├── requirements.txt
└── README.md
```



## Installation

### Prerequisites

### Installation instructions

1.  Run ``, and follow the instructions that appear.
2.  Get latest npm: `npm install -g npm@latest`
3.  Run `npm install`. This installs everything needed for the build to run successfully.
4.  Run `docker-compose pull` to pull down all images.

## Running the application
To start all of the supporting services (PostgresSQL, etc.):
`docker-compose up -d`

To start the FastAPI rest server and run the application at [http://localhost:3000](http://localhost:3000):
`uv dev-start`

This is in development mode and code changes will immediately be loaded without having to restart the server.



## Developers


### Frameworks

### Linter for Python 
Sinopia API uses [ruff].

`ruff run lint`

To auto-fix errors in both (where possible):
`npm run fix`

### Unit, feature, and integration tests

Tests are written with pytest.

To run all of the tests:
`uv run tests/`

To run a single test file (and see console messages):
`npx jest __tests__/endpoints/resourcePost.test.js`

To run a single test (and see console messages):
`npx jest __tests__/endpoints/resourcePost.test.js -t "returns 409 if resource is not unique"`

Or temporarily change the test description from `it("does something")` to `it.only("does something")` and run the single test file with `npx`.

#### Dev/Stage/Prod

#### Issuing queries

### Get a JWT

To authenticate:

#### Use JWT in HTTP Request

To use the JWT as stored in `.cognitoToken` to make authorized requests to Sinopia API, you can pass it along in the HTTP request as follows:

```shell
$ curl -i -H "Authorization: Bearer $(cat .cognitoToken)" http://localhost:3000/resource
```
