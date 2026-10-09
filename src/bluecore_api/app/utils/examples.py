"""
Executable request-body examples shown in the OpenAPI docs.

The JSON-LD ones are used by 'request_body_openapi' to populate the Swagger "Try
it out" forms for the Work, Instance, and Hub create/update endpoints. Each is a
valid, self-contained BIBFRAME resource that returns '201' when POSTed as-is.

MARCXML_EXAMPLE does the same job for the convert routes, which hand-write their
request bodies in app/routes/convert.py.
"""

from bluecore_api.constants import CONTEXT_URL

# The context is named by URL: the API refuses an inline one.
_CONTEXT = CONTEXT_URL

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


#: A single MARCXML record, enough of one to transform cleanly, so Swagger's
#: "Try it out" works as-is against /marc2bibframe.
MARCXML_EXAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<collection xmlns="http://www.loc.gov/MARC21/slim">
  <record>
    <leader>01142cam a2200301 a 4500</leader>
    <controlfield tag="001">92005291</controlfield>
    <controlfield tag="003">DLC</controlfield>
    <controlfield tag="008">920219s1993    caua          001 0 eng  </controlfield>
    <datafield tag="100" ind1="1" ind2=" ">
      <subfield code="a">Austen, Jane,</subfield>
      <subfield code="d">1775-1817.</subfield>
    </datafield>
    <datafield tag="245" ind1="1" ind2="0">
      <subfield code="a">Pride and prejudice /</subfield>
      <subfield code="c">Jane Austen.</subfield>
    </datafield>
  </record>
</collection>
"""
