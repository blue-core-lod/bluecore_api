"""
Executable JSON-LD request-body examples shown in the OpenAPI docs.

These are used by 'request_body_openapi' to populate the Swagger "Try it out"
forms for the Work, Instance, and Hub create/update endpoints. Each is a valid,
self-contained BIBFRAME resource that returns '201' when POSTed as-is.
"""

_CONTEXT = {
    "bf": "http://id.loc.gov/ontologies/bibframe/",
    "bflc": "http://id.loc.gov/ontologies/bflc/",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
}

WORK_EXAMPLE = {
    "@context": _CONTEXT,
    "@id": "https://api.sinopia.io/resources/example-work-0001",
    "@type": ["bf:Work", "bf:Text"],
    "rdfs:label": "Pride and prejudice",
    "bf:title": {"@type": "bf:Title", "bf:mainTitle": "Pride and prejudice"},
    "bf:language": {"@id": "http://id.loc.gov/vocabulary/languages/eng"},
    "bf:content": {"@id": "http://id.loc.gov/vocabulary/contentTypes/txt"},
    "bf:contribution": {
        "@type": "bf:Contribution",
        "bf:agent": {"@type": "bf:Agent", "rdfs:label": "Austen, Jane, 1775-1817"},
        "bf:role": {"@id": "http://id.loc.gov/vocabulary/relators/aut"},
    },
    "bf:classification": {
        "@type": "bf:ClassificationLcc",
        "bf:classificationPortion": "PR4034",
    },
}

INSTANCE_EXAMPLE = {
    "@context": _CONTEXT,
    "@id": "https://api.sinopia.io/resources/example-instance-0001",
    "@type": ["bf:Instance", "bf:Print"],
    "rdfs:label": "Pride and prejudice (Penguin Classics, 2003)",
    "bf:title": {"@type": "bf:Title", "bf:mainTitle": "Pride and prejudice"},
    "bf:provisionActivity": {
        "@type": "bf:Publication",
        "bf:agent": {"@type": "bf:Agent", "rdfs:label": "Penguin Books"},
        "bf:place": {"@type": "bf:Place", "rdfs:label": "London"},
        "bf:date": "2003",
    },
    "bf:identifiedBy": {"@type": "bf:Isbn", "rdf:value": "9780141439518"},
    "bf:extent": {"@type": "bf:Extent", "rdfs:label": "435 pages"},
}

HUB_EXAMPLE = {
    "@context": _CONTEXT,
    "@id": "https://api.sinopia.io/resources/example-hub-0001",
    "@type": "bf:Hub",
    "rdfs:label": "Austen, Jane, 1775-1817. Pride and prejudice",
    "bf:title": {"@type": "bf:Title", "bf:mainTitle": "Pride and prejudice"},
    "bf:language": {"@id": "http://id.loc.gov/vocabulary/languages/eng"},
    "bflc:aap": "Austen, Jane, 1775-1817. Pride and prejudice",
}
