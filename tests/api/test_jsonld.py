import pytest
from bluecore_models.utils.graph import CONTEXT_URL as BIBFRAME_CONTEXT_URL
from bluecore_models.utils.graph import load_jsonld

from bluecore_api.app.utils.jsonld import check_context, normalize_context
from bluecore_api.constants import CONTEXT_URL


def test_normalize_context_replaces_bluecore_context_url():
    data = normalize_context(
        {"@context": CONTEXT_URL, "@id": "https://bcld.info/works/1"}
    )

    assert data["@context"] == BIBFRAME_CONTEXT_URL  # ty: ignore[not-subscriptable]


def test_normalize_context_replaces_another_deployments_context_url():
    data = normalize_context({"@context": "https://localhost/api/context.jsonld"})

    assert data["@context"] == BIBFRAME_CONTEXT_URL  # ty: ignore[not-subscriptable]


def test_normalize_context_leaves_other_contexts_alone():
    data = normalize_context({"@context": "https://schema.org/"})

    assert data["@context"] == "https://schema.org/"  # ty: ignore[not-subscriptable]


def test_normalize_context_handles_a_list_of_nodes():
    data = normalize_context(
        [{"@context": CONTEXT_URL}, {"@id": "https://example.com/1"}]
    )

    assert data == [
        {"@context": BIBFRAME_CONTEXT_URL},
        {"@id": "https://example.com/1"},
    ]


def test_normalize_context_leaves_data_without_a_context_alone():
    data = normalize_context({"@id": "https://bcld.info/works/1"})

    assert data == {"@id": "https://bcld.info/works/1"}


def test_normalize_context_does_not_mutate_its_argument():
    original = {"@context": CONTEXT_URL}
    normalize_context(original)

    assert original == {"@context": CONTEXT_URL}


@pytest.mark.parametrize(
    "data",
    [
        {"@id": "https://bcld.info/works/1"},
        {"@context": BIBFRAME_CONTEXT_URL},
        [{"@context": BIBFRAME_CONTEXT_URL}, {"@id": "https://example.com/1"}],
    ],
)
def test_check_context_accepts_contexts_bluecore_models_reads(data):
    check_context(data)


@pytest.mark.parametrize(
    "context",
    [{"ex": "https://example.com/"}, "https://schema.org/", [BIBFRAME_CONTEXT_URL]],
)
def test_check_context_refuses_any_other_context(context):
    with pytest.raises(ValueError):
        check_context({"@context": context})


@pytest.mark.parametrize(
    "context_url", [CONTEXT_URL, "https://localhost/api/context.jsonld"]
)
def test_round_tripped_jsonld_parses_without_the_network(context_url, monkeypatch):
    """A body carrying a context URL must parse without resolving it."""

    def no_network(*args, **kwargs):
        raise AssertionError("attempted to resolve a remote context")

    monkeypatch.setattr("rdflib._networking._urlopen", no_network)

    graph = load_jsonld(
        normalize_context(
            {
                "@context": context_url,
                "@id": "https://bcld.info/works/1",
                "@type": "Work",
            }
        )  # ty: ignore[invalid-argument-type]
    )

    assert len(graph) == 1
