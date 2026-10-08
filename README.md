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

## 🔧 Environment

Next you will want to clone bluecore_api repository and create a `.env` file that will bring up the application using services that were brought up in the previous step. You should be able to use the following:

```text
# service uris
DATABASE_URL="postgresql://airflow:airflow@localhost/bluecore"
BLUECORE_URL="http://localhost:3000/"
API_URL="http://localhost:3000" # for the Blue Core Client: start-dev.sh serves the API at the bare root
AIRFLOW_INTERNAL_URL="http://localhost:8080"
KEYCLOAK_EXTERNAL_URL="http://localhost:8081/keycloak/"
KEYCLOAK_INTERNAL_URL="http://localhost:8081/keycloak/"
USE_KEYCLOAK_INTROSPECTION=false # Set to true only in development to start without keycloak

# keycloak config so blucore_api users can authenticate
API_KEYCLOAK_CLIENT_ID="bluecore_api"
API_KEYCLOAK_USER="developer"
API_KEYCLOAK_PASSWORD="123456"

# credentials so bluecore_api can talk to airflow
AIRFLOW_WWW_USER_USERNAME="airflow"
AIRFLOW_WWW_USER_PASSWORD="airflow"

# Editor Redirect URLs for HTML template views
MARVA_BASE_URL="http://localhost:4444/"
SINOPIA_BASE_URL="http://localhost:8888/"
```

## 💽 Running Migrations

Database migrations live in the separate [Blue Core Data Models] (`bluecore-models`) package. They are applied automatically for you by both start scripts before the server boots:

- `./start.sh` (Production) runs `uv run alembic upgrade head`, which uses the `[alembic]` section of `alembic.ini` (the `postgres` Docker database host).
- `./start-dev.sh` (Development) runs `uv run alembic --name dev upgrade head`, which uses the `[dev]` section (the `localhost` database host).


### Testing a migration from a local bluecore-models checkout

By default Alembic uses the migrations bundled with the installed `bluecore-models` package. To write and test a new migration against a local clone of [Blue Core Data Models] checked out next to this repo (`../bluecore-models`), point the `[dev]` section's `script_location` at that checkout in `alembic.ini`:

```ini
[dev]
script_location = ../bluecore-models/src/bluecore_models/migrations
prepend_sys_path = .
version_path_separator = os
sqlalchemy.url = postgresql+psycopg://airflow:airflow@localhost/bluecore
```

## 📂 Uploads Directory

The bluecore-workflows application has a `uploads` directory in it. You will need to create a symlink to it in your bluecore_api directory. This will allow files uploaded to the API to be available to the Airflow environment.

For example:

```shell
ln -s ../bluecore-workflows/uploads/ uploads 
```

## 🚀 Running the application

Two start scripts are provided. Both apply database migrations (see [Run Migrations](#run-migrations)) before launching the server:

- **`./start-dev.sh`** — local development. Runs the FastAPI dev server with autoreload on port `3000`, loads your `.env`, and migrates the `localhost` database. Use this for development.
- **`./start.sh`** — runs the app the way it runs in the container: FastAPI on port `8100` under the `/api` root path, migrating the `postgres` database host.

For local development with the environment file created above:

```shell
./start-dev.sh
```

The application should then be available at http://localhost:3000

## 🧑‍💻 Blue Core Client

Loading data and talking to the API by hand are both done with the [Blue Core Client]
(`bluecore-client`), a command line tool and Python library published on PyPI. It used
to live in this repository as a `bluecore` command; it now has its own repository.

```shell
uv tool install bluecore-client
```

It reads the same environment variable names as the API, so the `.env` created above is
picked up when you run `bluecore` from this directory. If your `.env` predates this
section, add the `API_URL` line from it — without that the client looks for the API under
`/api`, which the development server doesn't use, and every command 404s. To confirm
where it's pointed, and as whom:

```shell
bluecore whoami
```

`bluecore --help`, or `bluecore <command> --help`, covers the rest.

## 💾 Load Data

If you want to try loading some data:

```shell
bluecore --verbose load url https://raw.githubusercontent.com/blue-core-lod/bluecore_api/refs/heads/main/sample/batch.jsonld
```

This will tell the Blue Core API to load the data at that URL into the database. A local
file works too, in JSON-LD, turtle, RDF/XML or N-Triples, as does a zip or tar.gz archive
of RDF files:

```shell
bluecore load file sample/batch.jsonld
```

## 📇 Load Profiles

Resource profiles (e.g. Sinopia profiles) can be copied from another Blue Core instance
into your local one. By default the command pulls from `https://dev.bcld.info`:

```shell
bluecore load profiles
```

To pull from a different instance, pass its host as an argument:

```shell
bluecore load profiles https://stage.bcld.info
```

Each profile is created through the API rather than written to the database directly, so
your instance mints its own URI and rewrites the profile's resource template to match.
Note that this creates profiles rather than updating existing ones, so running it twice
loads two copies. Use `--dry-run` to see what would be loaded first.

## 📡 HTTP Requests

To talk directly to the API you will need to pass along a Keycloak access token. During development you can get one from the [Blue Core Client], which prints the token and nothing else:

```
curl --header "Authorization: Bearer $(bluecore token)" http://localhost:3000/change_documents/instances/page/1
```

### Authenticating in Swagger UI

`/docs` shows which routes require a token: protected operations carry a padlock and
document their 401 and 403 responses. The **Authorize** button runs a Keycloak login,
so you can exercise writes from the browser instead of pasting a token.

Two things have to line up for that button to work:

- `KEYCLOAK_EXTERNAL_URL` must point at the Keycloak your *browser* can reach.
  `KEYCLOAK_INTERNAL_URL` is what the server uses to validate tokens, and under
  Docker the two are different hostnames.
- The `bluecore_api` Keycloak client must list `<BLUECORE_URL>api/docs/oauth2-redirect`
  among its valid redirect URIs, and the origin serving `/docs` among its web origins.

If they don't, the spec still documents authentication correctly — only the in-browser
login fails, and the `curl` form above still works.

## 🔁 Converting MARC

Two endpoints convert MARC records, and both require the `create` role. The
[marc-bibframe] package runs the Library of Congress [marc2bibframe2] stylesheet in this
process, so no Airflow DAG sits in the path and the response comes back in the same
request.

`POST /marc2xml` turns binary MARC21 into MARCXML:

```shell
curl --header "Authorization: Bearer $(bluecore token)" \
  --header "Content-Type: application/marc" \
  --data-binary @record.mrc \
  http://localhost:3000/marc2xml
```

`POST /marc2bibframe` turns either binary MARC21 or MARCXML into BIBFRAME. Name the
serialization you want in `Accept`: `application/ld+json` (the default),
`application/rdf+xml`, `text/turtle` or `application/n-triples`.

```shell
curl --header "Authorization: Bearer $(bluecore token)" \
  --header "Content-Type: application/marc" \
  --header "Accept: text/turtle" \
  --data-binary @record.mrc \
  http://localhost:3000/marc2bibframe
```

Both also accept a `multipart/form-data` upload in a `file` field instead of a raw body,
which is how the Swagger "Try it out" form at `/docs` submits them.

Send one record. Both endpoints refuse a body holding more than one, or one larger than
`MAX_CONVERT_BYTES` (1 MB by default), with a `413`. They convert on the event loop and
answer synchronously, and the service runs a single worker, so an unbounded request would
stall every other call to the API: load testing with real Library of Congress records
measured 11 ms for one record against 9.5 s for a thousand.

Bulk MARC belongs in a batch workflow, which today means the [Blue Core Workflows]
`marc_to_bibframe` DAG: `/batches/upload/` passes its uploads to the `resource_loader` DAG,
and that reads JSON-LD rather than MARC.

MARCXML saved by a Windows editor often starts with an invisible byte order mark. That is
ignored, so such a file is still read as XML.

On top of the stylesheet's output, Blue Core names CBC rather than DLC as the assigner of
identifiers derived from the record. The bluecore-workflows `marc_to_bibframe` DAG applies
the same rewrite, so both routes into Blue Core agree.

### Base URIs

MARC does not identify most of what it describes, so the transform mints URIs for it, of the
form `{source_base_uri}{record id}#{fragment}`:

```shell
curl --header "Authorization: Bearer $(bluecore token)" \
  --header "Content-Type: application/xml" \
  --data-binary @record.xml \
  'http://localhost:3000/marc2bibframe?source_base_uri=https://example.edu/catalog/'
```

`source_base_uri` defaults to `http://example.org/`, which is marc-bibframe's own default and
is deliberately non-resolvable. These are not authority URIs. They are scoped to the record
they came from, so two records describing the same person give you two different agent URIs,
and reconciling those against an authority is your job once the endpoint hands back the graph.
Pass a base you control, and prefer one that cannot be mistaken for an authority's: minting
under `http://id.loc.gov/resources/` produces URIs that look like Library of Congress
identifiers but are not.

From Python, the [Blue Core Client] wraps the second endpoint:

```python
from bluecore_client import BluecoreClient

with BluecoreClient() as client:
    graph = client.convert.marc_to_bibframe("record.mrc")
    marcxml = client.convert.marc_to_xml("record.mrc")
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

## Type Checking

Bluecore API uses [ty]
- `uv run ty check`

[Blue Core Client]: https://github.com/blue-core-lod/bluecore-client
[Blue Core Data Models]: https://github.com/blue-core-lod/bluecore-models
[Blue Core Workflows]: https://github.com/blue-core-lod/bluecore-workflows
[ruff]: https://docs.astral.sh/ruff/
[uv]: https://github.com/astral-sh/uv
[Docker]: https://www.docker.com/
[marc2bibframe2]: https://github.com/lcnetdev/marc2bibframe2
[marc-bibframe]: https://github.com/blue-core-lod/marc-bibframe
