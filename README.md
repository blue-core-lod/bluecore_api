# Blue Core API

Blue Core API is a REST API for managing Blue Core resources and workflows using PostgreSQL and Airflow platforms. The application relies on Keycloak and Airflow services. To understand the production deployment of Blue Core API you'll want to look at the [Terraform](https://github.com/blue-core-lod/terraform) repository.

Read on for instructions about how to develop this codebase.

## 🧰 Prerequisites
- [uv]
- [Docker]

## Setup PostgreSQL, Keycloak and Airflow

Blue Core API depends on having PostgreSQL, Airflow and Keycloak running. The easiest way to do this is to clone the [Blue Core Workflows] repository, and start the default configuration:

```shell
git clone https://github.com/blue-core-lod/bluecore-workflows
cd bluecore-workflows
docker compose up 
```

## Database Models

The Blue Core API depends on database models in the [Blue Core Data Models] to be present and up to date.

```shell
git clone https://github.com/blue-core-lod/bluecore-models
cd bluecore-models
uv run alembic upgrade head
```
 
## 🔧 Environment

Next you will want to clone bluecore_api repository and create a `.env` file that will bring up the application using services that were brought up in the previous step. You should be able to use the following:

```text
# service uris
DATABASE_URL="postgresql://airflow:airflow@localhost/bluecore"
BLUECORE_URL="http://localhost:3000/"
AIRFLOW_INTERNAL_URL="http://localhost:8080"
KEYCLOAK_EXTERNAL_URL="http://localhost:8081/keycloak/"
KEYCLOAK_INTERNAL_URL="http://localhost:8081/keycloak/"

# keycloak config so blucore_api users can authenticate
API_KEYCLOAK_CLIENT_ID="bluecore_api"
API_KEYCLOAK_USER="developer"
API_KEYCLOAK_PASSWORD="123456"

# credentials so bluecore_api can talk to airflow
AIRFLOW_WWW_USER_USERNAME="airflow"
AIRFLOW_WWW_USER_PASSWORD="airflow"
```

## 💾 Uploads Directory

The bluecore-workflows application has a `uploads` directory in it. You will need to create a symlink to it in your bluecore_api directory. This will allow files uploaded to the API to be available to the Airflow environment.

For example:

```shell
ln -s ../bluecore-workflows/uploads/ uploads 
```

## 🚀 Running the application

Now you are ready to start the application using your new environment file and the fastapi development server, which will auto-load any changes you make to the code:

```shell
uv run dotenv run fastapi dev src/bluecore_api/app/main.py --port 3000
```

## Load Data

If you want to try loading some data you can use the `bluecore` utility:

```shell
uv run bluecore load sample/batch.jsonld 
```

This will load a batch of data to the bluecore_api API, and tell [Blue Core Workflows] to load it.

## HTTP Requests

To talk directly to the API you will need to pass along a Keycloak access token. During development you can get one by using the included `bluecore` command line tool:

```
export TOKEN=`uv run bluecore token`
curl --header "Authorization: Bearer ${TOKEN}" http://localhost:3000/change_documents/instances/page/1
```

## 🧹 Linting

Bluecore API uses [ruff]
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

[Blue Core Data Models]: https://github.com/blue-core-lod/bluecore-models
[Blue Core Workflows]: https://github.com/blue-core-lod/bluecore-workflows
[ruff]: https://docs.astral.sh/ruff/
[uv]: https://github.com/astral-sh/uv
[Docker]: https://www.docker.com/
