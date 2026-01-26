import json

from typing import Union

from bluecore_models.models import Instance, Work
from bluecore_models.utils.graph import load_jsonld


def expand_resource_graph(db_resource: Union[Instance, Work]) -> list:
    """
    Takes a Bluecore Work or Instance and iterates through the entity's
    other resources and adds the other resource RDF to the entity's graph.
    """
    expanded_graph = load_jsonld(db_resource.data)
    for row in db_resource.other_resources:
        other_resource_graph = load_jsonld(row.other_resource.data)
        expanded_graph.parse(
            data=other_resource_graph.serialize(format="json-ld"), format="json-ld"
        )
    return json.loads(expanded_graph.serialize(format="json-ld"))
