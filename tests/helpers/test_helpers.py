import pytest

from bluecore.helpers.graph import init_graph, generate_entity_graph

def test_init_graph():
    graph = init_graph()
    assert graph.namespace_manager.qname("http://id.loc.gov/ontologies/bibframe/") == "bf:"
    assert graph.namespace_manager.qname("http://id.loc.gov/ontologies/bflc/") == "bflc:"
    assert graph.namespace_manager.qname("http://www.loc.gov/mads/rdf/v1#") == "mads:"