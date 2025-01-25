import rdflib
import torch

from transformers import AutoTokenizer, AutoModel

BF = rdflib.Namespace("http://id.loc.gov/ontologies/bibframe/")
BFLC = rdflib.Namespace("http://id.loc.gov/ontologies/bflc/")
LCLOCAL = rdflib.Namespace("http://id.loc.gov/ontologies/lclocal/")
MADS = rdflib.Namespace("http://www.loc.gov/mads/rdf/v1#")


def init_graph() -> rdflib.Graph:
    new_graph = rdflib.Graph()
    new_graph.namespace_manager.bind("bf", "http://id.loc.gov/ontologies/bibframe/")
    new_graph.namespace_manager.bind("bflc", "http://id.loc.gov/ontologies/bflc/")
    new_graph.namespace_manager.bind("mads", "http://www.loc.gov/mads/rdf/v1#")
    return new_graph


def _check_for_namespace(node) -> bool:
    return node in LCLOCAL or node in rdflib.DCTERMS


def _expand_bnode(graph: rdflib.Graph, entity_graph: rdflib.Graph, bnode: rdflib.BNode):
    for pred, obj in graph.predicate_objects(subject=bnode):
        if _check_for_namespace(pred) or _check_for_namespace(obj):
            continue
        entity_graph.add((bnode, pred, obj))
        if isinstance(obj, rdflib.BNode):
            _expand_bnode(graph, entity_graph, obj)


def generate_embedding(input_string, vector_size, model_name="bert-base-uncased"):
    """
    Generate a 768-dimensional embedding for the given input string, compatible with pgvector.

    Args:
        input_string (str): The input string to embed.
        model_name (str): Pre-trained model name (default is "bert-base-uncased").

    Returns:
        list[float]: A 768-dimensional embedding of the input string, as a list of floats.
    """
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name)

    # Tokenize input string
    inputs = tokenizer(input_string, return_tensors="pt", truncation=True, max_length=vector_size)

    # Forward pass through the model
    with torch.no_grad():
        outputs = model(**inputs)

    # Extract the CLS token embedding (ColBERT uses CLS token for aggregation)
    cls_embedding = outputs.last_hidden_state[:, 0, :].squeeze(0)

    # Convert the tensor to a list of floats for pgvector compatibility
    embedding_vector = cls_embedding.cpu().numpy().tolist()

    return embedding_vector

def generate_entity_graph(graph: rdflib.Graph, entity: rdflib.URIRef) -> rdflib.Graph:
    entity_graph = init_graph()
    for pred, obj in graph.predicate_objects(subject=entity):
        if _check_for_namespace(pred) or _check_for_namespace(obj):
            continue
        entity_graph.add((entity, pred, obj))
        if isinstance(obj, rdflib.BNode):
            _expand_bnode(graph, entity_graph, obj)
    return entity_graph
