"""Build profiles shaped like the ones sinopia_editor saves: expanded JSON-LD."""

from dataclasses import dataclass, field
from itertools import count

S = "http://sinopia.io/vocabulary/"
BF = "http://id.loc.gov/ontologies/bibframe/"
RDFS_LABEL = "http://www.w3.org/2000/01/rdf-schema#label"
BCLD = "https://bcld.info"

_ids = count()


def profile_uri(n: int) -> str:
    return f"{BCLD}/profiles/00000000-0000-0000-0000-{n:012d}"


def version(n: int, v: int) -> str:
    return f"{profile_uri(n)}/version/{v}"


@dataclass
class Prop:
    uri: str
    type: str = "literal"
    more_uris: tuple[str, ...] = ()
    required: bool = False
    repeatable: bool = False
    ordered: bool = False
    datatype: str | None = None
    regex: str | None = None
    nested: tuple[str, ...] = ()
    label: str = "a property"
    defaults: tuple[str, ...] = field(default_factory=tuple)

    def nodes(self) -> tuple[str, list[dict]]:
        n = next(_ids)
        node: dict = {
            "@id": f"_:p{n}",
            "@type": [f"{S}PropertyTemplate"],
            RDFS_LABEL: [{"@value": self.label}],
            f"{S}hasPropertyUri": [{"@id": u} for u in (self.uri, *self.more_uris)],
            f"{S}hasPropertyType": [{"@id": f"{S}propertyType/{self.type}"}],
        }
        attributes = [
            f"{S}propertyAttribute/{name}"
            for name in ("required", "repeatable", "ordered")
            if getattr(self, name)
        ]
        if attributes:
            node[f"{S}hasPropertyAttribute"] = [{"@id": a} for a in attributes]
        nodes = [node]
        if self.type == "literal" and (self.datatype or self.regex or self.defaults):
            literal: dict = {"@id": f"_:l{n}"}
            if self.datatype:
                literal[f"{S}hasValidationDataType"] = [{"@id": self.datatype}]
            if self.regex:
                literal[f"{S}hasValidationRegex"] = [{"@value": self.regex}]
            if self.defaults:
                literal[f"{S}hasDefault"] = [{"@value": d} for d in self.defaults]
            node[f"{S}hasLiteralAttributes"] = [{"@id": literal["@id"]}]
            nodes.append(literal)
        if self.type == "resource":
            resource = {
                "@id": f"_:r{n}",
                f"{S}hasResourceTemplateId": [{"@id": ref} for ref in self.nested],
            }
            node[f"{S}hasResourceAttributes"] = [{"@id": resource["@id"]}]
            nodes.append(resource)
        return node["@id"], nodes


def template(
    cls: str,
    *props: Prop,
    uri: str = "https://example.com/templates/t",
    optional_classes: tuple[str, ...] = (),
    suppressible: bool = False,
    label: str = "A template",
    resource_id: str = "test:template",
) -> list[dict]:
    root: dict = {
        "@id": uri,
        "@type": [f"{S}ResourceTemplate"],
        f"{S}hasResourceId": [{"@value": resource_id}],
        RDFS_LABEL: [{"@value": label}],
        f"{S}hasClass": [{"@id": cls}],
    }
    if optional_classes:
        root[f"{S}hasOptionalClass"] = [{"@id": c} for c in optional_classes]
    if suppressible:
        root[f"{S}hasResourceAttribute"] = [
            {"@id": f"{S}resourceAttribute/suppressible"}
        ]
    nodes = [root]
    ids = []
    for prop in props:
        prop_id, prop_nodes = prop.nodes()
        ids.append({"@id": prop_id})
        nodes += prop_nodes
    if ids:
        root[f"{S}hasPropertyTemplate"] = [{"@list": ids}]
    return nodes
