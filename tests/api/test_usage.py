from bluecore_models.models import BibframeOtherResources, Instance, OtherResource, Work

HEADERS = {"X-User": "cataloger"}

PYNCHON = "http://id.loc.gov/rwo/agents/n79099184"
POSTMODERNISM = "http://id.loc.gov/authorities/subjects/sh95008451"
AUT = "http://id.loc.gov/vocabulary/relators/aut"
EDT = "http://id.loc.gov/vocabulary/relators/edt"


def _contribution(agent: str, *roles: str) -> dict:
    return {
        "@type": ["Contribution"],
        "agent": [{"@id": agent}],
        "role": [{"@id": role} for role in roles],
    }


def _work(id_: int, title: str, **props: list) -> Work:
    return Work(
        id=id_,
        uri=f"https://bcld.info/works/{id_}",
        data={
            "@id": f"https://bcld.info/works/{id_}",
            "@type": ["Work", "Text"],
            "title": [{"@type": ["Title"], "mainTitle": [title]}],
            **props,
        },
    )


def _link(db_session, other: OtherResource, *resources) -> None:
    for resource in resources:
        db_session.add(
            BibframeOtherResources(
                other_resource_id=other.id, bibframe_resource_id=resource.id
            )
        )


def _library(db_session) -> None:
    """Pynchon wrote one Work and edited another; a third is about postmodernism."""
    pynchon = OtherResource(id=7001, uri=PYNCHON, data={"@id": PYNCHON})
    topic = OtherResource(id=7002, uri=POSTMODERNISM, data={"@id": POSTMODERNISM})
    lot49 = _work(
        7101,
        "The crying of lot 49",
        contribution=[_contribution(PYNCHON, AUT)],
        subject=[{"@id": POSTMODERNISM}],
    )
    anthology = _work(
        7102,
        "An anthology",
        contribution=[
            _contribution("http://id.loc.gov/rwo/agents/n00000001", AUT),
            _contribution(PYNCHON, EDT),
        ],
    )
    criticism = _work(7103, "On Pynchon", subject=[{"@id": POSTMODERNISM}])
    db_session.add_all([pynchon, topic, lot49, anthology, criticism])
    db_session.flush()
    instances = [
        Instance(
            id=7200 + n, uri=f"https://bcld.info/instances/{n}", data={}, work_id=work
        )
        for n, work in enumerate([7101, 7101, 7101, 7102, 7103])
    ]
    db_session.add_all(instances)
    _link(db_session, pynchon, lot49, anthology)
    _link(db_session, topic, lot49, criticism)
    db_session.commit()


def test_counts_works_records_and_roles_for_a_name(client, db_session):
    _library(db_session)
    # Asked by the authority URI, found by the real-world-object URI Blue Core stores.
    resp = client.get(
        "/usage/",
        params={"uri": "https://id.loc.gov/authorities/names/n79099184"},
        headers=HEADERS,
    )
    assert resp.status_code == 200, resp.text
    usage = resp.json()
    assert usage["works"] == 2
    assert usage["instances"] == 0
    assert usage["records"] == 4
    assert usage["used_as"] == {"contribution": 2}
    assert usage["roles"] == {AUT: 1, EDT: 1}
    by_title = {work["title"]: work for work in usage["recent_works"]}
    assert by_title["The crying of lot 49"]["instances"] == 3
    assert by_title["An anthology"]["uri"] == "https://bcld.info/works/7102"


def test_counts_a_subject(client, db_session):
    _library(db_session)
    usage = client.get("/usage/", params={"uri": POSTMODERNISM}, headers=HEADERS).json()
    assert usage["works"] == 2
    assert usage["records"] == 4
    assert usage["used_as"] == {"subject": 2}
    assert usage["roles"] == {}
    assert usage["equivalents"] == [POSTMODERNISM]


def test_names_an_untitled_work_by_its_instance(client, db_session):
    topic = OtherResource(id=7003, uri=POSTMODERNISM, data={"@id": POSTMODERNISM})
    untitled = Work(
        id=7104,
        uri="https://bcld.info/works/7104",
        data={"@id": "https://bcld.info/works/7104", "@type": ["Work"]},
    )
    db_session.add_all([topic, untitled])
    db_session.flush()
    db_session.add(
        Instance(
            id=7300,
            uri="https://bcld.info/instances/7300",
            data={
                "@id": "https://bcld.info/instances/7300",
                "@type": ["Instance"],
                "title": [{"@type": ["Title"], "mainTitle": ["The end"]}],
            },
            work_id=7104,
        )
    )
    _link(db_session, topic, untitled)
    db_session.commit()
    usage = client.get("/usage/", params={"uri": POSTMODERNISM}, headers=HEADERS).json()
    assert [work["title"] for work in usage["recent_works"]] == ["The end"]


def test_reports_nothing_for_an_entity_blue_core_does_not_use(client, db_session):
    usage = client.get(
        "/usage/",
        params={"uri": "http://id.loc.gov/authorities/names/n00000002"},
        headers=HEADERS,
    ).json()
    assert usage["works"] == 0
    assert usage["records"] == 0
    assert usage["recent_works"] == []


def test_refuses_what_is_not_a_uri(client):
    resp = client.get("/usage/", params={"uri": "Pynchon"}, headers=HEADERS)
    assert resp.status_code == 422
