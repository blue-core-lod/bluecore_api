"""HTML search grouping of OtherResources into per-type sections."""

from bluecore_models.models import OtherResource

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


def _add(db_session, id_, bf_type, slug, is_profile=False):
    uri = f"https://id.loc.gov/x/{slug}"
    db_session.add(
        OtherResource(
            id=id_,
            uri=uri,
            is_profile=is_profile,
            data=_authority(uri, bf_type, f"{TOKEN} {slug}"),
        )
    )
    return uri


def test_other_resources_grouped_into_sections(client, db_session):
    person = _add(db_session, 6001, "Person", "a-person")
    topic = _add(db_session, 6002, "Topic", "a-topic")
    hub = _add(db_session, 6003, "Hub", "a-hub")
    classif = _add(db_session, 6004, "Classification", "a-class")
    lang = _add(db_session, 6005, "Language", "a-lang")
    profile = _add(db_session, 6006, "Person", "a-profile", is_profile=True)
    db_session.commit()

    resp = client.get("/search", params={"q": TOKEN, "type": "all"})
    assert resp.status_code == 200
    body = resp.text

    # All OtherResources live in the "Other Resources" panel...
    assert ">Other Resources</h2>" in body
    # ...each kind under its own section heading (now <h3> within the panel).
    for heading in [
        "Name Authorities",
        "Subjects",
        "Hubs",
        "LC Classifications",
        "Vocabularies",
    ]:
        assert f">{heading}</h3>" in body, heading

    # Links present for the non-profile authorities, absent for the profile.
    for uri in (person, topic, hub, classif, lang):
        assert f'href="{uri}"' in body, uri
    assert f'href="{profile}"' not in body

    # Section order: Name Authorities before Subjects before Hubs (per OTHER_SECTION_ORDER).
    assert body.index("Name Authorities") < body.index("Subjects") < body.index("Hubs")


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
    assert ">Works</h3>" in resp.text
