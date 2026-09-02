import pytest
from bluecore_models.utils.graph import CONTEXT, load_jsonld

from bluecore_api.app.utils.jsonld import inline_context
from bluecore_api.constants import CONTEXT_URL


def test_inline_context_replaces_bluecore_context_url():
    data = inline_context({"@context": CONTEXT_URL, "@id": "https://bcld.info/works/1"})

    assert data["@context"] == CONTEXT  # ty: ignore[not-subscriptable]


def test_inline_context_replaces_another_deployments_context_url():
    """Data downloaded from one deployment can be sent back to another."""
    data = inline_context({"@context": "https://localhost/api/context.jsonld"})

    assert data["@context"] == CONTEXT  # ty: ignore[not-subscriptable]


def test_inline_context_leaves_other_contexts_alone():
    data = inline_context({"@context": "https://schema.org/"})

    assert data["@context"] == "https://schema.org/"  # ty: ignore[not-subscriptable]


def test_inline_context_replaces_reference_in_a_list():
    data = inline_context({"@context": [CONTEXT_URL, {"ex": "https://example.com/"}]})

    assert data["@context"] == [CONTEXT, {"ex": "https://example.com/"}]  # ty: ignore[not-subscriptable]


def test_inline_context_handles_a_list_of_nodes():
    data = inline_context([{"@context": CONTEXT_URL}, {"@id": "https://example.com/1"}])

    assert data == [{"@context": CONTEXT}, {"@id": "https://example.com/1"}]


def test_inline_context_leaves_data_without_a_context_alone():
    data = inline_context({"@id": "https://bcld.info/works/1"})

    assert data == {"@id": "https://bcld.info/works/1"}


def test_inline_context_does_not_mutate_its_argument():
    original = {"@context": CONTEXT_URL}
    inline_context(original)

    assert original == {"@context": CONTEXT_URL}


@pytest.mark.parametrize(
    "context_url", [CONTEXT_URL, "https://localhost/api/context.jsonld"]
)
def test_round_tripped_jsonld_parses_without_the_network(context_url, monkeypatch):
    """A body carrying a context URL must parse without resolving it."""

    def no_network(*args, **kwargs):
        raise AssertionError("attempted to resolve a remote context")

    monkeypatch.setattr("rdflib._networking._urlopen", no_network)

    graph = load_jsonld(
        inline_context(
            {
                "@context": context_url,
                "@id": "https://bcld.info/works/1",
                "@type": "Work",
            }
        )  # ty: ignore[invalid-argument-type]
    )

    assert len(graph) == 1
