import os
from pathlib import Path

import dotenv
import httpx
from rich import print as printr
from typer import Argument, Exit, Option, Typer
from typing_extensions import Annotated

dotenv.load_dotenv()
app = Typer()
state = {}


@app.command()
def token():
    """
    Get a Keycloak access token for a given user.
    """
    try:
        token = _get_token()
        # use regular print here so newlines aren't inserted into the token
        print(token, end="")
    except httpx.HTTPError as e:
        printr(f"[red]{e}[/red]")
        raise Exit(1)


@app.command()
def root():
    """
    Get a Keycloak access token for a given user.
    """
    try:
        token = _get_token()

        resp = httpx.get(
            f"{state['bluecore_url']}/",
            headers={"Authorization": f"Bearer {token}"},
        )
        printr(resp)

    except httpx.HTTPError as e:
        printr(f"[red]{e}[/red]")
        raise Exit(1)


@app.command()
def load(
    file: Annotated[
        Path, Argument(exists=True, dir_okay=False, readable=True, resolve_path=True)
    ],
):
    """
    Upload a Bibframe JSON-LD file as a batch import.
    """
    try:
        token = _get_token()

        resp = httpx.post(
            f"{state['bluecore_url']}/batches/upload/",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": file.open("rb")},
        )

        resp.raise_for_status()
        printr(resp.json())

    except httpx.HTTPError as e:
        printr(f"[red]{e}[/red]")
        raise Exit(1)


@app.callback()
def main(
    bluecore_url: Annotated[str, Option(help="Bluecore URL")] = None,
    username: Annotated[str, Option(help="Bluecore username")] = None,
    password: Annotated[str, Option(help="Bluecore password")] = None,
    verbose: Annotated[bool, Option(help="Verbose output")] = False,
):
    # set some global options either from the command line, a .env or a prompt
    env = os.getenv
    state["bluecore_url"] = (
        bluecore_url or env("BLUECORE_URL") or input("Bluecore URL: ")
    )
    state["username"] = (
        username or env("API_KEYCLOAK_USER") or input("Bluecore Username: ")
    )
    state["password"] = (
        password or env("API_KEYCLOAK_PASSWORD") or input("Bluecore Password: ")
    )
    state["verbose"] = verbose

    # usually the Keycloak URL is the same as the BlueCore URL, but sometimes in
    # development it's helpful to specify it separately
    state["keycloak_url"] = env("KEYCLOAK_URL") or state["bluecore_url"]

    # remove trailing slashes from URLs
    state["bluecore_url"] = state["bluecore_url"].rstrip("/")
    state["keycloak_url"] = state["keycloak_url"].rstrip("/")

    if verbose:
        printr("\n[bold]Configuration:[/bold]")
        for k, v in state.items():
            printr(f"[bold]{k}[/bold]: {v}")


def _get_token():
    resp = httpx.post(
        f"{state['keycloak_url']}/realms/bluecore/protocol/openid-connect/token",
        data={
            "client_id": "bluecore_api",  # this is hardcoded
            "username": state["username"],
            "password": state["password"],
            "grant_type": "password",
        },
    )

    resp.raise_for_status()

    return resp.json().get("access_token")


if __name__ == "__main__":
    app()
