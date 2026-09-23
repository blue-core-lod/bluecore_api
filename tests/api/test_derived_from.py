"""Looking up the Blue Core resource derived from an external record."""

import pytest
from bluecore_models.models import Instance, Work
from sqlalchemy.orm import Session

from bluecore_api.derived_from import find_by_derived_from, uri_variants

LC_WORK = "http://id.loc.gov/resources/works/23118629"


def _resource(model, id_, uri, derived_from):
    return model(
        id=id_,
        uuid=f"00000000-0000-0000-0000-0000000001{id_:02d}",
        uri=uri,
        data={
            "@id": uri,
            "@type": model.__name__,
            "title": {"@type": "Title", "mainTitle": "whatever"},
            "adminMetadata": [
                {"@type": "AdminMetadata", "derivedFrom": {"@id": derived_from}}
            ],
        },
    )


@pytest.fixture
def copied(db_session: Session, client) -> str:
    uri = "https://bcld.info/works/00000000-0000-0000-0000-000000000101"
    db_session.add(_resource(Work, 1, uri, LC_WORK))
    # Same provenance, different type: the lookup must not cross types.
    db_session.add(
        _resource(
            Instance,
            2,
            "https://bcld.info/instances/00000000-0000-0000-0000-000000000102",
            LC_WORK,
        )
    )
    db_session.commit()
    return uri


def test_finds_the_resource_derived_from_an_external_uri(db_session, copied):
    assert find_by_derived_from(db_session, [LC_WORK], "works") == {LC_WORK: copied}


def test_the_lookup_is_scoped_to_one_type(db_session, copied):
    """Not cosmetic. The backing index is (type, derivedFrom), so without a
    predicate on type Postgres cannot seek and scans the whole index --
    measured at 243ms for a 25-URI page over 84k rows, against 1.1ms with it."""
    found = find_by_derived_from(db_session, [LC_WORK], "instances")

    assert list(found) == [LC_WORK]
    assert found[LC_WORK].startswith("https://bcld.info/instances/")


def test_unheld_uris_are_absent_rather_than_null(db_session, copied):
    other = "http://id.loc.gov/resources/works/99999999"

    found = find_by_derived_from(db_session, [LC_WORK, other], "works")

    assert other not in found


def test_either_scheme_matches_what_was_stored(db_session, copied):
    """id.loc.gov publishes http URIs but redirects browsers to https, so
    which form got stored depends on how the record arrived."""
    https = LC_WORK.replace("http://", "https://")

    assert find_by_derived_from(db_session, [https], "works") == {https: copied}


def test_no_uris_means_no_query(db_session):
    assert find_by_derived_from(db_session, [], "works") == {}


def test_uri_variants_covers_both_schemes():
    assert set(uri_variants("http://example.com/a")) == {
        "http://example.com/a",
        "https://example.com/a",
    }
    assert uri_variants("urn:x:1") == ["urn:x:1"]
