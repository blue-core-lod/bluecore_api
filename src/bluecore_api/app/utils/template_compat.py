"""Whether existing records can move to a proposed version of their profile.

sinopia_editor writes a record by walking its template (GraphBuilder.js) and
reads it back by walking the template again (resourceHelpers.js), so a template
change breaks a record when a triple the record actually has could no longer be
read back, or would be written in a different shape. See
blue-core-lod/bluecore_api#339 for the table of changes this follows.

Nested templates are chosen the way the editor's loader chooses them, including
the suppressible rules sinopia_editor#168 introduced (selectResourceTemplateId,
resolveAmbiguousChildRtIds and selectSuppressibleResourceTemplateId).
"""

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

from bluecore_models.models import Profile
from fastapi import HTTPException
from rdflib import RDF, Graph, Literal, Namespace, URIRef
from rdflib.collection import Collection
from rdflib.term import Node
from sqlalchemy import select
from sqlalchemy.orm import Session

from bluecore_api.app.utils.jsonld import load_jsonld_from_model
from bluecore_api.app.utils.profile_usage import pinned_records
from bluecore_api.app.utils.profile_versions import VERSION_URI, resolve_version_uri

SINOPIA = Namespace("http://sinopia.io/vocabulary/")
PROPERTY_TYPE = str(SINOPIA["propertyType/"])
REQUIRED = SINOPIA["propertyAttribute/required"]
REPEATABLE = SINOPIA["propertyAttribute/repeatable"]
ORDERED = SINOPIA["propertyAttribute/ordered"]
SUPPRESSIBLE = SINOPIA["resourceAttribute/suppressible"]
LABEL_SUPPRESSED = SINOPIA["uriAttribute/labelSuppressed"]
RDFS_LABEL = URIRef("http://www.w3.org/2000/01/rdf-schema#label")


class TemplateError(ValueError):
    """The data does not describe exactly one resource template."""


@dataclass
class PropertyTemplate:
    uris: tuple[str, ...]
    type: str
    required: bool = False
    repeatable: bool = False
    ordered: bool = False
    datatype: str | None = None
    regex: str | None = None
    # hasResourceTemplateId values, as written: versioned URIs, plain profile
    # URIs, or bare template ids.
    nested: tuple[str, ...] = ()
    # Only reported, never breaking.
    label: str | None = None
    remark: str | None = None
    remark_url: str | None = None
    defaults: frozenset[str] = frozenset()
    authorities: frozenset[str] = frozenset()
    label_suppressed: bool = False


@dataclass
class ResourceTemplate:
    uri: str | None = None
    resource_id: str | None = None
    label: str | None = None
    remark: str | None = None
    required_class: str | None = None
    # hasClass and hasOptionalClass: the editor types a record with all of them,
    # and picks a nested template by any of them.
    classes: frozenset[str] = frozenset()
    suppressible: bool = False
    # Keyed by each hasPropertyUri, so reordering the property list changes
    # nothing. A tuple, because two nested-resource property templates may
    # share a predicate when their nested classes differ (sinopia_editor#168).
    properties: dict[str, tuple[PropertyTemplate, ...]] = field(default_factory=dict)

    def property_templates(self) -> list[PropertyTemplate]:
        """Each property template once, though it is listed under every URI."""
        unique: dict[int, PropertyTemplate] = {}
        for templates in self.properties.values():
            for template in templates:
                unique.setdefault(id(template), template)
        return list(unique.values())


EMPTY = ResourceTemplate()

# Looks up the template a reference names (a versioned or plain profile URI),
# or None if it can't. TemplateCache is the one the API uses.
TemplateLookup = Callable[[str], ResourceTemplate | None]


def _str(node: Node | None) -> str | None:
    return None if node is None else str(node)


def _objects(graph: Graph, subject: Node | None, predicate: URIRef) -> list[Node]:
    if subject is None:
        return []
    return list(graph.objects(subject, predicate))


def _value(graph: Graph, subject: Node | None, predicate: URIRef) -> str | None:
    """One value as a string, if subject (an optional attributes node) has it."""
    return None if subject is None else _str(graph.value(subject, predicate))


def _property_template(graph: Graph, node: Node) -> PropertyTemplate:
    attributes = set(_objects(graph, node, SINOPIA.hasPropertyAttribute))
    literal = graph.value(node, SINOPIA.hasLiteralAttributes)
    resource = graph.value(node, SINOPIA.hasResourceAttributes)
    uri = graph.value(node, SINOPIA.hasUriAttributes)
    lookup = graph.value(node, SINOPIA.hasLookupAttributes)
    defaults = {
        str(default)
        for attribute in (literal, resource, uri, lookup)
        for default in _objects(graph, attribute, SINOPIA.hasDefault)
    }
    nested = _objects(graph, resource, SINOPIA.hasResourceTemplateId)
    return PropertyTemplate(
        uris=tuple(sorted(str(u) for u in graph.objects(node, SINOPIA.hasPropertyUri))),
        type=str(graph.value(node, SINOPIA.hasPropertyType) or "").removeprefix(
            PROPERTY_TYPE
        ),
        required=REQUIRED in attributes,
        repeatable=REPEATABLE in attributes,
        ordered=ORDERED in attributes,
        datatype=_value(graph, literal, SINOPIA.hasValidationDataType),
        regex=_value(graph, literal, SINOPIA.hasValidationRegex),
        nested=tuple(sorted(str(n) for n in nested)),
        label=_str(graph.value(node, RDFS_LABEL)),
        remark=_str(graph.value(node, SINOPIA.hasRemark)),
        remark_url=_str(graph.value(node, SINOPIA.hasRemarkUrl)),
        defaults=frozenset(defaults),
        authorities=frozenset(
            str(a) for a in _objects(graph, lookup, SINOPIA.hasAuthority)
        ),
        label_suppressed=LABEL_SUPPRESSED
        in _objects(graph, uri, SINOPIA.hasUriAttribute),
    )


def parse_template(graph: Graph) -> ResourceTemplate:
    """The parts of a profile that decide whether a record still fits it.

    The Python counterpart of the parts of sinopia_editor's TemplatesBuilder.js
    that GraphBuilder.js and resourceHelpers.js depend on.
    """
    roots = set(graph.subjects(RDF.type, SINOPIA.ResourceTemplate))
    if len(roots) != 1:
        raise TemplateError(
            f"expected one sinopia:ResourceTemplate, found {len(roots)}"
        )
    root = roots.pop()
    required_class = _str(graph.value(root, SINOPIA.hasClass))
    classes = {str(c) for c in graph.objects(root, SINOPIA.hasOptionalClass)}
    if required_class is not None:
        classes.add(required_class)

    head = graph.value(root, SINOPIA.hasPropertyTemplate)
    nodes = [] if head is None else list(Collection(graph, head))
    properties: dict[str, list[PropertyTemplate]] = {}
    for node in nodes:
        template = _property_template(graph, node)
        for uri in template.uris:
            properties.setdefault(uri, []).append(template)

    resource_attributes = set(graph.objects(root, SINOPIA.hasResourceAttribute))
    return ResourceTemplate(
        uri=str(root),
        resource_id=_str(graph.value(root, SINOPIA.hasResourceId)),
        label=_str(graph.value(root, RDFS_LABEL)),
        remark=_str(graph.value(root, SINOPIA.hasRemark)),
        required_class=required_class,
        classes=frozenset(classes),
        suppressible=SUPPRESSIBLE in resource_attributes,
        properties={
            uri: tuple(sorted(templates, key=lambda t: (t.nested, t.type)))
            for uri, templates in properties.items()
        },
    )


def stored_template(data) -> ResourceTemplate:
    """Parse a stored profile or version.

    Stored data that describes no template (rows written before profiles were
    minted a ResourceTemplate node) reads as an empty template rather than an
    error: nothing was made with it that it could break.
    """
    graph = load_jsonld_from_model(data)
    if not any(graph.subjects(RDF.type, SINOPIA.ResourceTemplate)):
        return EMPTY
    return parse_template(graph)


def profile_key(ref: str) -> str:
    """The profile a nested reference names, whichever version it pins."""
    match = VERSION_URI.fullmatch(ref)
    return match["profile_uri"] if match else ref


class TemplateCache:
    """Look up nested and pinned templates, parsing each one once per request.

    A versioned URI resolves to that version, a plain profile URI to the
    profile as it is now. Anything else (a bare template id such as
    pcc:bf2:Title) or anything not stored resolves to None. unresolved() lists
    those, so a response can say which templates its checks could not see.
    """

    def __init__(self, db: Session):
        self.db = db
        self._cache: dict[str, ResourceTemplate | None] = {}

    def __call__(self, ref: str) -> ResourceTemplate | None:
        if ref not in self._cache:
            self._cache[ref] = self._load(ref)
        return self._cache[ref]

    def unresolved(self) -> list[str]:
        """Every reference looked up so far that could not be loaded."""
        return sorted(ref for ref, found in self._cache.items() if found is None)

    def _load(self, ref: str) -> ResourceTemplate | None:
        if VERSION_URI.fullmatch(ref):
            try:
                _, version = resolve_version_uri(self.db, ref)
            except HTTPException:
                return None
            data = version.data
        else:
            profile = (
                self.db.execute(select(Profile).where(Profile.uri == ref))
                .scalars()
                .first()
            )
            if profile is None:
                return None
            data = profile.data
        try:
            return stored_template(data)
        except (ValueError, TypeError):
            return None


# --- What changed between two versions of a profile ---------------------------


@dataclass
class Change:
    kind: str
    property: str | None
    detail: str
    breaking: bool


Candidates = list[tuple[str, ResourceTemplate]]


def _candidates(refs: Iterable[str], nested_templates: TemplateLookup) -> Candidates:
    return [(ref, t) for ref in refs if (t := nested_templates(ref)) is not None]


def _ambiguous_classes(candidates: Candidates) -> set[str]:
    """Classes the editor could not pick a single nested template for.

    Mirrors validateUniqueResourceURIs: several candidates may share a class
    only if exactly one of them is non-suppressible.
    """
    ambiguous = set()
    for _, template in candidates:
        clazz = template.required_class
        if clazz is None:
            continue
        sharing = [t for _, t in candidates if clazz in t.classes]
        if len(sharing) > 1 and sum(not t.suppressible for t in sharing) != 1:
            ambiguous.add(clazz)
    return ambiguous


def _nested_changes(
    old: PropertyTemplate,
    new: PropertyTemplate,
    uri: str,
    nested_templates: TemplateLookup,
    seen: set[tuple[str, str]],
) -> list[Change]:
    changes = []

    def change(kind: str, detail: str, breaking: bool):
        changes.append(Change(kind, uri, detail, breaking))

    old_refs = {profile_key(ref): ref for ref in old.nested}
    new_refs = {profile_key(ref): ref for ref in new.nested}
    for profile, old_ref in old_refs.items():
        new_ref = new_refs.get(profile)
        if new_ref is None:
            change("nested_removed", f"nested template {old_ref} removed", True)
        elif new_ref != old_ref:
            # A bump to a newer version of the same profile only breaks
            # records if that nested diff does.
            detail = f"nested template {old_ref} -> {new_ref}"
            old_nested = nested_templates(old_ref)
            new_nested = nested_templates(new_ref)
            if old_nested is None or new_nested is None:
                # Can't compare what can't be loaded, so don't call it safe.
                unloadable = [
                    ref
                    for ref, found in ((old_ref, old_nested), (new_ref, new_nested))
                    if found is None
                ]
                detail += f" (could not load {', '.join(unloadable)} to compare)"
                breaking = True
            elif (old_ref, new_ref) in seen:
                breaking = False  # already being compared, further up
            else:
                seen.add((old_ref, new_ref))
                breaking = old_nested.suppressible != new_nested.suppressible or any(
                    c.breaking
                    for c in _template_changes(
                        old_nested, new_nested, nested_templates, seen
                    )
                )
            change("nested_version_changed", detail, breaking)
    for profile, new_ref in new_refs.items():
        if profile not in old_refs:
            change("nested_added", f"nested template {new_ref} added", False)

    old_candidates = _candidates(old.nested, nested_templates)
    new_candidates = _candidates(new.nested, nested_templates)
    newly_ambiguous = _ambiguous_classes(new_candidates) - _ambiguous_classes(
        old_candidates
    )
    for clazz in sorted(newly_ambiguous):
        change(
            "nested_ambiguous",
            f"more than one non-suppressible nested template has class {clazz}",
            True,
        )
    old_suppressible = sum(t.suppressible for _, t in old_candidates)
    new_suppressible = sum(t.suppressible for _, t in new_candidates)
    if old_suppressible == 1 and new_suppressible > 1:
        change(
            "nested_ambiguous",
            "more than one suppressible nested template, so a bare URI matches none",
            True,
        )
    return changes


SAFE_PROPERTY_FIELDS = (
    "label",
    "remark",
    "remark_url",
    "defaults",
    "authorities",
    "label_suppressed",
)


def _property_changes(
    old: PropertyTemplate,
    new: PropertyTemplate,
    uri: str,
    nested_templates: TemplateLookup,
    seen: set[tuple[str, str]],
) -> list[Change]:
    changes = []

    def change(kind: str, detail: str, breaking: bool):
        changes.append(Change(kind, uri, detail, breaking))

    if old.type != new.type:
        change("type_changed", f"property type {old.type} -> {new.type}", True)
        return changes
    if old.ordered != new.ordered:
        change("ordered_changed", f"ordered {old.ordered} -> {new.ordered}", True)
    if old.required != new.required:
        change(
            "required_changed",
            f"required {old.required} -> {new.required}",
            new.required,
        )
    if old.repeatable != new.repeatable:
        change(
            "repeatable_changed",
            f"repeatable {old.repeatable} -> {new.repeatable}",
            not new.repeatable,
        )
    if old.datatype != new.datatype:
        change("datatype_changed", f"datatype {old.datatype} -> {new.datatype}", True)
    if old.regex != new.regex:
        change("regex_changed", f"validation regex {old.regex} -> {new.regex}", True)
    if new.type == "resource":
        changes += _nested_changes(old, new, uri, nested_templates, seen)
    for name in SAFE_PROPERTY_FIELDS:
        if getattr(old, name) != getattr(new, name):
            change(f"{name}_changed", f"{name} changed", False)
    return changes


def _shares_profile(old: PropertyTemplate, new: PropertyTemplate) -> bool:
    profiles = {profile_key(ref) for ref in old.nested}
    return bool(profiles & {profile_key(ref) for ref in new.nested})


def _counterpart(
    old: PropertyTemplate, new: Sequence[PropertyTemplate]
) -> PropertyTemplate | None:
    """The property template in new that old most likely became.

    Almost always the only one for the predicate. When several nested-resource
    templates share it, the one offering the same nested profile.
    """
    if len(new) == 1:
        return new[0]
    same_type = [n for n in new if n.type == old.type]
    return next((n for n in same_type if _shares_profile(old, n)), None) or next(
        iter(same_type), None
    )


def _template_changes(
    old: ResourceTemplate,
    new: ResourceTemplate,
    nested_templates: TemplateLookup,
    seen: set[tuple[str, str]],
) -> list[Change]:
    changes = []
    for clazz in sorted(old.classes - new.classes):
        changes.append(Change("class_removed", None, f"class {clazz} removed", True))
    for clazz in sorted(new.classes - old.classes):
        changes.append(Change("class_added", None, f"class {clazz} added", False))
    if old.required_class != new.required_class:
        changes.append(
            Change(
                "required_class_changed",
                None,
                f"class {old.required_class} -> {new.required_class}",
                old.required_class is not None
                and old.required_class not in new.classes,
            )
        )
    if old.suppressible != new.suppressible:
        changes.append(
            Change(
                "suppressible_changed",
                None,
                f"suppressible {old.suppressible} -> {new.suppressible}",
                True,
            )
        )
    for name in ("label", "remark", "resource_id"):
        if getattr(old, name) != getattr(new, name):
            changes.append(Change(f"{name}_changed", None, f"{name} changed", False))

    for uri in sorted(old.properties.keys() | new.properties.keys()):
        unpaired = list(new.properties.get(uri, ()))
        for o in old.properties.get(uri, ()):
            n = _counterpart(o, unpaired)
            if n is None:
                changes.append(
                    Change("property_removed", uri, "property removed", True)
                )
                continue
            unpaired.remove(n)
            changes += _property_changes(o, n, uri, nested_templates, seen)
        for n in unpaired:
            detail = "required property added" if n.required else "property added"
            changes.append(Change("property_added", uri, detail, n.required))
    return changes


def template_changes(
    old: ResourceTemplate, new: ResourceTemplate, nested_templates: TemplateLookup
) -> list[Change]:
    """Every difference from old to new, each marked breaking or safe.

    Breaking means a record *could* be affected; whether any is depends on its
    data, which breaking_changes checks.
    """
    return _template_changes(old, new, nested_templates, set())


# --- Whether a record can move to the new version ------------------------------


@dataclass
class Problem:
    subject: str
    property: str | None
    reason: str


@dataclass
class Match:
    ref: str
    template: ResourceTemplate
    suppressed: bool


class Ambiguous:
    """The editor would refuse to choose between several nested templates."""


AMBIGUOUS = Ambiguous()


def _has_values(graph: Graph, node: Node, template: ResourceTemplate) -> bool:
    """Whether the editor would fill any of the template's fields for node."""
    return any((node, URIRef(uri), None) in graph for uri in template.properties)


def _single_suppressible(
    candidates: Candidates,
) -> tuple[str, ResourceTemplate] | None:
    suppressible = [c for c in candidates if c[1].suppressible]
    return suppressible[0] if len(suppressible) == 1 else None


def select_nested(
    graph: Graph, value: Node, refs: Iterable[str], nested_templates: TemplateLookup
) -> Match | Ambiguous | None:
    """The nested template the editor would load value with (resourceHelpers.js).

    Returns a Match, AMBIGUOUS when the editor would refuse to choose, or None
    when nothing matches (the value would be dropped or left as unused RDF).
    """
    candidates = _candidates(refs, nested_templates)
    if not candidates:
        return None
    types = {str(t) for t in graph.objects(value, RDF.type)}
    matched = [c for c in candidates if c[1].classes & types]
    if len(matched) > 1:
        # resolveAmbiguousChildRtIds: prefer the one non-suppressible match.
        matched = [c for c in matched if not c[1].suppressible]
        if len(matched) != 1:
            return AMBIGUOUS
    named = isinstance(value, URIRef)
    if matched:
        ref, template = matched[0]
        if named and template.suppressible:
            return Match(ref, template, True)
        if not _has_values(graph, value, template):
            # Only a type: a blank node is dropped, a URI falls back to the
            # suppressible sibling when there is exactly one.
            if not named:
                return None
            sibling = _single_suppressible(candidates)
            if sibling is not None:
                return Match(*sibling, True)
        return Match(ref, template, False)
    # No local type matched: a bare URI goes to the one suppressible candidate.
    if named:
        sibling = _single_suppressible(candidates)
        if sibling is not None:
            return Match(*sibling, True)
    return None


def _values(graph: Graph, objects: list[Node], ordered: bool) -> list[Node]:
    """A property's values, reading through the rdf:List an ordered one is."""
    if not ordered:
        return objects
    values: list[Node] = []
    for obj in objects:
        if obj == RDF.nil or graph.value(obj, RDF.first) is not None:
            values += list(Collection(graph, obj))
        else:
            values.append(obj)
    return values


def _assign(
    templates: tuple[PropertyTemplate, ...],
    graph: Graph,
    objects: list[Node],
    nested_templates: TemplateLookup,
) -> list[tuple[PropertyTemplate, list[Node]]]:
    """Which of a predicate's property templates each value belongs to."""
    if len(templates) == 1:
        return [(templates[0], _values(graph, objects, templates[0].ordered))]
    assigned = []
    for template in templates:
        values = [
            v
            for v in _values(graph, objects, template.ordered)
            if isinstance(
                select_nested(graph, v, template.nested, nested_templates), Match
            )
        ]
        if values:
            assigned.append((template, values))
    return assigned


def _literal_datatype(value: Literal) -> str | None:
    return _str(value.datatype)


def _nested_reason(
    before: Match, after: Match | Ambiguous | None, unloadable: list[str]
) -> str | None:
    if after is None and unloadable:
        refs = ", ".join(unloadable)
        return f"could not load nested template {refs} to check it against"
    if after is None:
        return f"no nested template matches it any more (was {before.ref})"
    if isinstance(after, Ambiguous):
        return "more than one nested template would match it"
    if profile_key(after.ref) != profile_key(before.ref):
        return f"nested template changed from {before.ref} to {after.ref}"
    if after.template.suppressible != before.template.suppressible:
        return "nested suppressible flag changed"
    if after.suppressed != before.suppressed:
        return "it would be written in a different shape (suppressed or not)"
    return None


def _nested_problems(
    old: PropertyTemplate,
    new: PropertyTemplate,
    graph: Graph,
    uri: str,
    values: list[Node],
    nested_templates: TemplateLookup,
    seen: set[tuple[Node, str, str]],
) -> list[Problem]:
    problems = []
    unloadable = [ref for ref in new.nested if nested_templates(ref) is None]
    for value in values:
        before = select_nested(graph, value, old.nested, nested_templates)
        if not isinstance(before, Match):
            continue  # it could not be read back under the old version either
        after = select_nested(graph, value, new.nested, nested_templates)
        reason = _nested_reason(before, after, unloadable)
        if reason is not None:
            problems.append(Problem(str(value), uri, reason))
        elif isinstance(after, Match) and after.ref != before.ref:
            # A version bump of the same profile: check the nested resource
            # against it, unless it is a suppressed URI with nothing to check.
            key = (value, before.ref, after.ref)
            if not before.suppressed and key not in seen:
                seen.add(key)
                problems += _breaking_changes(
                    before.template,
                    after.template,
                    graph,
                    value,
                    nested_templates,
                    seen,
                )
    return problems


def _literal_problems(
    old: PropertyTemplate, new: PropertyTemplate, values: list[Node]
) -> list[str]:
    reasons = []
    literals = [v for v in values if isinstance(v, Literal)]
    if new.datatype != old.datatype and any(
        _literal_datatype(v) != new.datatype for v in literals
    ):
        reasons.append(f"datatype -> {new.datatype}")
    if new.regex and new.regex != old.regex:
        try:
            pattern = re.compile(new.regex)
        except re.error:
            # JavaScript regex syntax Python can't read: unknown, not broken.
            return reasons
        # Sinopia tests with new RegExp(r).test(v), which is a search.
        if any(not pattern.search(str(v)) for v in literals):
            reasons.append(f"a value does not match {new.regex}")
    return reasons


def _property_problems(
    old: PropertyTemplate,
    new: PropertyTemplate,
    graph: Graph,
    subject: str,
    uri: str,
    values: list[Node],
    nested_templates: TemplateLookup,
    seen: set[tuple[Node, str, str]],
) -> list[Problem]:
    if new.type != old.type:
        return [Problem(subject, uri, f"property type {old.type} -> {new.type}")]
    reasons = []
    if new.ordered != old.ordered:
        reasons.append("ordered flag changed")
    if old.repeatable and not new.repeatable and len(values) > 1:
        reasons.append("no longer repeatable, but it has more than one value")
    if new.type == "literal":
        reasons += _literal_problems(old, new, values)
    problems = [Problem(subject, uri, reason) for reason in reasons]
    if new.type == "resource":
        problems += _nested_problems(
            old, new, graph, uri, values, nested_templates, seen
        )
    return problems


def _breaking_changes(
    old: ResourceTemplate,
    new: ResourceTemplate,
    graph: Graph,
    subject: Node,
    nested_templates: TemplateLookup,
    seen: set[tuple[Node, str, str]],
) -> list[Problem]:
    name = str(subject)
    problems = []
    types = {str(t) for t in graph.objects(subject, RDF.type)}
    for clazz in sorted(types & (old.classes - new.classes)):
        reason = f"class {clazz} is no longer in the template"
        problems.append(Problem(name, str(RDF.type), reason))

    for uri, old_templates in old.properties.items():
        objects = list(graph.objects(subject, URIRef(uri)))
        if not objects:
            continue
        new_templates = new.properties.get(uri, ())
        if not new_templates:
            reason = "property removed; its data would become unused RDF"
            problems.append(Problem(name, uri, reason))
            continue
        for template, values in _assign(
            old_templates, graph, objects, nested_templates
        ):
            counterpart = _counterpart(template, new_templates) or new_templates[0]
            problems += _property_problems(
                template, counterpart, graph, name, uri, values, nested_templates, seen
            )

    for template in new.property_templates():
        if not template.required:
            continue
        was_required = any(
            o.required for u in template.uris for o in old.properties.get(u, ())
        )
        has_value = any((subject, URIRef(u), None) in graph for u in template.uris)
        if not was_required and not has_value:
            uri = template.uris[0] if template.uris else None
            problems.append(Problem(name, uri, "newly required, but it has no value"))
    return problems


def breaking_changes(
    old: ResourceTemplate,
    new: ResourceTemplate,
    graph: Graph,
    subject: Node,
    nested_templates: TemplateLookup,
) -> list[Problem]:
    """What would stop subject, made with old, from moving to new.

    Only data the record actually has is checked, so a breaking change no record
    uses reports nothing here.
    """
    return _breaking_changes(old, new, graph, subject, nested_templates, set())


@dataclass
class IncompatibleInstance:
    uri: str
    version_uri: str
    problems: list[Problem]


def incompatible_instances(
    db: Session,
    profile: Profile,
    proposed: ResourceTemplate,
    templates: TemplateLookup,
) -> list[IncompatibleInstance]:
    """The records pinned to a version of this profile that couldn't move to it.

    Only records whose root template is this profile are checked. Records pinned
    to a plain profile URI are skipped, since they name no version to compare.
    templates looks up both the version each record is pinned to and the nested
    templates; pass a TemplateCache so each is parsed once.
    """
    found = []
    for uri, version_uri, data in pinned_records(db, profile):
        pinned = templates(version_uri)
        if pinned is None:
            continue
        graph = load_jsonld_from_model(data)
        pointer = URIRef(version_uri)
        root = next(graph.subjects(SINOPIA.hasResourceTemplate, pointer), None)
        if root is None:
            continue
        problems = breaking_changes(
            pinned, proposed, graph, root, nested_templates=templates
        )
        if problems:
            found.append(IncompatibleInstance(uri, version_uri, problems))
    return found
