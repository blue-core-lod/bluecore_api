"""OtherResources are excluded from HTML search (pending feedback)."""

from bluecore_models.models import OtherResource, Profile

BF = "http://id.loc.gov/ontologies/bibframe/"
RDFS_LABEL = "http://www.w3.org/2000/01/rdf-schema#label"
TOKEN = "kumaesection"


def _authority(uri: str, bf_type: str, label: str) -> list[dict]:
    return [
        {
            "@id": uri,
            "@type": [f"{BF}{bf_type}"],
            RDFS_LABEL: [{"@value": label}],
        }
    ]


def _add(db_session, id_, bf_type, slug):
    uri = f"https://id.loc.gov/x/{slug}"
    db_session.add(
        OtherResource(
            id=id_,
            uri=uri,
            data=_authority(uri, bf_type, f"{TOKEN} {slug}"),
        )
    )
    return uri


def test_other_resources_excluded_from_search(client, db_session):
    # OtherResources (authorities, agents, subjects) and Profiles should not
    # show up in the resource search for now.
    person = _add(db_session, 6001, "Person", "a-person")
    topic = _add(db_session, 6002, "Topic", "a-topic")
    hub = _add(db_session, 6003, "Hub", "a-hub")
    profile_uri = "https://id.loc.gov/x/a-profile"
    db_session.add(
        Profile(
            id=6006,
            uri=profile_uri,
            data=_authority(profile_uri, "Person", f"{TOKEN} a-profile"),
        )
    )
    db_session.commit()

    resp = client.get("/search", params={"q": TOKEN, "type": "all"})
    assert resp.status_code == 200
    body = resp.text

    # None of the OtherResource / Profile links appear in the results.
    for uri in (person, topic, hub, profile_uri):
        assert f'href="{uri}"' not in body, uri


def test_single_type_search_shows_heading(client, db_session):
    from bluecore_models.models import Work

    db_session.add(
        Work(
            id=6100,
            uuid="00000000-0000-0000-0000-000000006100",
            uri="https://bcld.info/works/00000000-0000-0000-0000-000000006100",
            data=_authority(
                "https://bcld.info/works/00000000-0000-0000-0000-000000006100",
                "Work",
                f"{TOKEN} a-work",
            ),
        )
    )
    db_session.commit()
    resp = client.get("/search", params={"q": TOKEN, "type": "works"})
    assert resp.status_code == 200
    assert ">Works</h2>" in resp.text
