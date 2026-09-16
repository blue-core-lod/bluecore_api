from __future__ import annotations

from datetime import datetime

import pytest
from bluecore_models.models import Hub, Instance, Work
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from bluecore_api.constants import CONTEXT_URL

WORK_UUID = "370ccc0a-3280-4036-9ca1-d9b5d5daf7df"
OTHER_WORK_UUID = "9c1a2b3d-4e5f-4a6b-8c7d-0e1f2a3b4c5d"
INSTANCE_UUID = "5c1d0a6e-1f2b-4c3d-9e8f-7a6b5c4d3e2f"
HUB_UUID = "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d"

ORIGINAL_TITLE = "first title"
UPDATED_TITLE = "second title"
# bluecore-models >=0.30.0 frames every property as a list, even a single value
# (frame_jsonld -> _as_arrays). The seeds below stay scalar -- framing happens
# on write -- so reads have to expect the wrapped form.
FRAMED_ORIGINAL_TITLE = [ORIGINAL_TITLE]
FRAMED_UPDATED_TITLE = [UPDATED_TITLE]


def add_work(db: Session, *, id: int = 1, uuid: str = WORK_UUID) -> Work:
    uri = f"https://bcld.info/works/{uuid}"
    work = Work(
        id=id,
        uuid=uuid,
        uri=uri,
        data={"@id": uri, "@type": "Work", "title": ORIGINAL_TITLE},
    )
    db.add(work)
    db.commit()
    return work


def update_work(db: Session, work: Work, title: str = UPDATED_TITLE) -> None:
    # The ** splat preserves @id and @type; reassigning .data is what marks the
    # row dirty, which is what makes add_version() write a second row.
    work.data = {**work.data, "title": title}  # ty: ignore[invalid-assignment, invalid-argument-type]
    db.commit()


def test_work_versions_lists_create_then_update(
    client: TestClient, db_session: Session
) -> None:
    work = add_work(db_session)
    update_work(db_session, work)

    response = client.get(f"/works/{WORK_UUID}/versions")

    assert response.status_code == 200
    versions = response.json()["versions"]
    assert len(versions) == 2
    # sinopia_editor reverses this list and treats the head as newest, so the
    # API has to hand back oldest first.
    assert versions[0]["id"] < versions[1]["id"]
    assert versions[0]["timestamp"] < versions[1]["timestamp"]


def test_work_versions_response_is_wrapped_in_a_versions_key(
    client: TestClient, db_session: Session
) -> None:
    # fetchResourceVersions() reads json.versions, so a bare array would
    # silently deserialize to undefined in the editor.
    add_work(db_session)

    response = client.get(f"/works/{WORK_UUID}/versions")

    assert response.status_code == 200
    assert isinstance(response.json(), dict)
    assert list(response.json()) == ["versions"]


def test_version_list_omits_the_jsonld_payload(
    client: TestClient, db_session: Session
) -> None:
    # A resource with a long edit history would return megabytes per row if the
    # list query loaded Version.data.
    add_work(db_session)

    response = client.get(f"/works/{WORK_UUID}/versions")

    entry = response.json()["versions"][0]
    assert set(entry) == {"id", "timestamp", "user"}
    assert "data" not in entry


@pytest.fixture
def user_context():
    """
    Set the context vars add_version() reads when it writes a Version, and
    restore them afterwards so the vars do not leak between tests.
    """
    from bluecore_models.models.version import CURRENT_USER_ID, CURRENT_USERNAME

    tokens = []

    def _set(uid: str | None = None, username: str | None = None) -> None:
        tokens.append((CURRENT_USER_ID, CURRENT_USER_ID.set(uid)))
        tokens.append((CURRENT_USERNAME, CURRENT_USERNAME.set(username)))

    yield _set

    for var, token in reversed(tokens):
        var.reset(token)


UID = "8f3c1a2e-4b5d-4c6d-8e7f-0a1b2c3d4e5f"


def test_version_user_is_the_username_when_recorded(
    client: TestClient, db_session: Session, user_context
) -> None:
    # The whole point of keycloak_username: catalogers see a name, not a GUID.
    user_context(uid=UID, username="jgreben")
    add_work(db_session)

    response = client.get(f"/works/{WORK_UUID}/versions")

    assert response.json()["versions"][0]["user"] == "jgreben"


def test_version_user_falls_back_to_the_uid(
    client: TestClient, db_session: Session, user_context
) -> None:
    # preferred_username is absent from some tokens, so a uid with no username
    # is a normal case rather than an edge one. A GUID beats a blank author.
    user_context(uid=UID, username=None)
    add_work(db_session)

    response = client.get(f"/works/{WORK_UUID}/versions")

    assert response.json()["versions"][0]["user"] == UID


def test_version_user_falls_back_to_unknown(
    client: TestClient, db_session: Session
) -> None:
    # Batch ingest and migrations write versions with no user context at all,
    # leaving both columns NULL. VersionSchema.user is a plain str, so the
    # route has to supply something rather than emitting a null the editor
    # would interpolate verbatim as "by null".
    add_work(db_session)

    response = client.get(f"/works/{WORK_UUID}/versions")

    assert response.json()["versions"][0]["user"] == "unknown"


def test_version_timestamp_is_utc_designated(
    client: TestClient, db_session: Session
) -> None:
    # Without the trailing Z, JavaScript parses an offset-less date-time as
    # local time and every "N hours ago" label drifts by the viewer's offset.
    add_work(db_session)

    timestamp = client.get(f"/works/{WORK_UUID}/versions").json()["versions"][0][
        "timestamp"
    ]

    assert timestamp.endswith("Z")
    assert datetime.fromisoformat(timestamp.removesuffix("Z"))


def test_version_timestamp_round_trips_to_a_fetch(
    client: TestClient, db_session: Session
) -> None:
    # The editor echoes the string it was given straight back into the URL, so
    # formatting and parsing have to agree exactly.
    work = add_work(db_session)
    update_work(db_session, work)

    versions = client.get(f"/works/{WORK_UUID}/versions").json()["versions"]
    oldest = versions[0]["timestamp"]

    response = client.get(f"/works/{WORK_UUID}/version/{oldest}")

    assert response.status_code == 200
    assert response.json()["data"]["title"] == FRAMED_ORIGINAL_TITLE


def test_version_can_be_fetched_by_integer_id(
    client: TestClient, db_session: Session
) -> None:
    # MCP clients get both identifiers and should prefer the unambiguous one.
    work = add_work(db_session)
    update_work(db_session, work)

    versions = client.get(f"/works/{WORK_UUID}/versions").json()["versions"]

    response = client.get(f"/works/{WORK_UUID}/version/{versions[0]['id']}")

    assert response.status_code == 200
    assert response.json()["data"]["title"] == FRAMED_ORIGINAL_TITLE


def test_newest_version_matches_the_live_resource(
    client: TestClient, db_session: Session
) -> None:
    work = add_work(db_session)
    update_work(db_session, work)

    versions = client.get(f"/works/{WORK_UUID}/versions").json()["versions"]
    newest = client.get(f"/works/{WORK_UUID}/version/{versions[-1]['id']}").json()
    live = client.get(
        f"/works/{WORK_UUID}", headers={"Accept": "application/vnd.sinopia+json"}
    ).json()

    assert newest["data"]["title"] == FRAMED_UPDATED_TITLE
    assert newest["data"] == live["data"]


def test_version_payload_carries_identity_and_context(
    client: TestClient, db_session: Session
) -> None:
    work = add_work(db_session)
    update_work(db_session, work)

    versions = client.get(f"/works/{WORK_UUID}/versions").json()["versions"]
    payload = client.get(f"/works/{WORK_UUID}/version/{versions[0]['id']}").json()

    # Identity comes from the live resource; only data comes from the snapshot.
    assert payload["uuid"] == WORK_UUID
    assert payload["uri"] == f"https://bcld.info/works/{WORK_UUID}"
    assert payload["type"] == "works"
    # Version.data is stored without @context; the route re-injects it, and the
    # editor's datasetFromJsonld() cannot parse the graph without it.
    assert payload["data"]["@context"] == CONTEXT_URL


def test_fetching_a_version_does_not_create_one(
    client: TestClient, db_session: Session
) -> None:
    # add_version() fires from after_insert/after_update, so a read path that
    # flushed a resource would silently write history while browsing it.
    work = add_work(db_session)
    update_work(db_session, work)

    before = client.get(f"/works/{WORK_UUID}/versions").json()["versions"]
    client.get(f"/works/{WORK_UUID}/version/{before[0]['id']}")
    after = client.get(f"/works/{WORK_UUID}/versions").json()["versions"]

    assert before == after


def test_versions_of_unknown_work_are_404(client: TestClient) -> None:
    response = client.get(f"/works/{OTHER_WORK_UUID}/versions")

    assert response.status_code == 404


def test_version_of_another_resource_is_not_reachable(
    client: TestClient, db_session: Session
) -> None:
    # The resource_id filter is a boundary: without it, any version id resolves
    # under any resource's URL.
    add_work(db_session, id=1, uuid=WORK_UUID)
    other = add_work(db_session, id=2, uuid=OTHER_WORK_UUID)
    update_work(db_session, other, title="other title")

    other_versions = client.get(f"/works/{OTHER_WORK_UUID}/versions").json()["versions"]
    stolen_id = other_versions[0]["id"]

    response = client.get(f"/works/{WORK_UUID}/version/{stolen_id}")

    assert response.status_code == 404


def test_malformed_version_identifier_is_400(
    client: TestClient, db_session: Session
) -> None:
    add_work(db_session)

    response = client.get(f"/works/{WORK_UUID}/version/not-a-timestamp")

    assert response.status_code == 400


def test_instance_versions(client: TestClient, db_session: Session) -> None:
    work = add_work(db_session)
    uri = f"https://bcld.info/instances/{INSTANCE_UUID}"
    instance = Instance(
        id=2,
        uuid=INSTANCE_UUID,
        uri=uri,
        work_id=work.id,
        data={"@id": uri, "@type": "Instance", "title": ORIGINAL_TITLE},
    )
    db_session.add(instance)
    db_session.commit()
    # get_db closes the session after each request, detaching these objects, so
    # read anything we need to assert on before the first client call.
    work_id = work.id

    listed = client.get(f"/instances/{INSTANCE_UUID}/versions")
    assert listed.status_code == 200
    versions = listed.json()["versions"]
    assert len(versions) == 1

    payload = client.get(f"/instances/{INSTANCE_UUID}/version/{versions[0]['id']}")
    assert payload.status_code == 200
    assert payload.json()["work_id"] == work_id
    assert payload.json()["data"]["title"] == FRAMED_ORIGINAL_TITLE


def test_hub_versions(client: TestClient, db_session: Session) -> None:
    uri = f"https://bcld.info/hubs/{HUB_UUID}"
    hub = Hub(
        id=3,
        uuid=HUB_UUID,
        uri=uri,
        data={"@id": uri, "@type": "Hub", "title": ORIGINAL_TITLE},
    )
    db_session.add(hub)
    db_session.commit()

    listed = client.get(f"/hubs/{HUB_UUID}/versions")
    assert listed.status_code == 200
    versions = listed.json()["versions"]
    assert len(versions) == 1

    payload = client.get(f"/hubs/{HUB_UUID}/version/{versions[0]['id']}")
    assert payload.status_code == 200
    assert payload.json()["type"] == "hubs"


def test_version_endpoints_are_public_gets(
    client: TestClient, keycloak_client: TestClient, db_session: Session
) -> None:
    # /works/ is already a BypassKeycloakForGet prefix, so the nested version
    # paths inherit it. That is implicit -- assert it so a change to
    # PREFIX_PATHS cannot lock the editor out without failing a test.
    add_work(db_session)

    listed = keycloak_client.get(f"/works/{WORK_UUID}/versions")
    assert listed.status_code == 200

    version_id = listed.json()["versions"][0]["id"]
    assert (
        keycloak_client.get(f"/works/{WORK_UUID}/version/{version_id}").status_code
        == 200
    )


if __name__ == "__main__":
    pytest.main()
