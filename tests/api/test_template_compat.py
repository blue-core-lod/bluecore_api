"""Unit tests for template_compat: no database, nested templates from a dict."""

import pytest
from bluecore_models.utils.graph import load_jsonld
from rdflib import Graph, URIRef
from sinopia_templates import BF, Prop, profile_uri, template, version

from bluecore_api.app.utils.template_compat import (
    AMBIGUOUS,
    Match,
    TemplateCache,
    TemplateError,
    breaking_changes,
    parse_template,
    record_problems,
    select_nested,
    template_changes,
)

XSD_DATE = "http://www.w3.org/2001/XMLSchema#date"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
RECORD = URIRef("https://bcld.info/works/w1")


def parse(data):
    return parse_template(load_jsonld(data))


def record(turtle: str) -> Graph:
    return Graph().parse(
        data=f"@prefix bf: <{BF}> .\n@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
        + turtle,
        format="turtle",
    )


def lookup(**templates):
    """A TemplateLookup over a fixed set of nested templates, keyed by reference."""
    return lambda ref: templates.get(ref)


NONE = lookup()


def reasons(old, new, graph, nested_templates=NONE, subject=RECORD):
    return [
        p.reason
        for p in breaking_changes(
            old, new, graph, subject, nested_templates=nested_templates
        )
    ]


def breaking(old, new, nested_templates=NONE):
    changes = template_changes(old, new, nested_templates=nested_templates)
    return {c.kind for c in changes if c.breaking}


WORK = f"{BF}Work"
NOTE = Prop(f"{BF}note", repeatable=True)
DATE = Prop(f"{BF}date")


# --- parsing --------------------------------------------------------------------


def test_parse_template():
    parsed = parse(
        template(
            WORK,
            Prop(f"{BF}title", "resource", required=True, nested=(version(1, 3),)),
            Prop(f"{BF}date", datatype=XSD_DATE, regex="^\\d{4}$"),
            Prop(f"{BF}note", repeatable=True, ordered=True),
            optional_classes=(f"{BF}Text",),
        )
    )

    assert parsed.required_class == WORK
    assert parsed.classes == {WORK, f"{BF}Text"}
    title = parsed.properties[f"{BF}title"][0]
    assert (title.type, title.required, title.nested) == (
        "resource",
        True,
        (version(1, 3),),
    )
    date = parsed.properties[f"{BF}date"][0]
    assert (date.datatype, date.regex) == (XSD_DATE, "^\\d{4}$")
    note = parsed.properties[f"{BF}note"][0]
    assert (note.repeatable, note.ordered) == (True, True)


def test_parse_lists_a_template_under_each_of_its_uris():
    parsed = parse(template(WORK, Prop(f"{BF}note", more_uris=(f"{BF}summary",))))

    assert parsed.properties[f"{BF}note"] == parsed.properties[f"{BF}summary"]
    assert len(parsed.property_templates()) == 1


@pytest.mark.parametrize("roots", [0, 2])
def test_parse_needs_one_resource_template(roots):
    data = [node for _ in range(roots) for node in template(WORK)]
    for n, node in enumerate(data):
        if "@type" in node:
            node["@id"] = f"https://example.com/t{n}"

    with pytest.raises(TemplateError):
        parse(data)


# --- safe changes ----------------------------------------------------------------


def test_safe_edits_report_changes_but_break_nothing():
    old = parse(template(WORK, NOTE, DATE))
    new = parse(
        template(
            WORK,
            Prop(f"{BF}note", repeatable=True, label="Notes", defaults=("n/a",)),
            DATE,
            Prop(f"{BF}extent"),  # a new optional property
            optional_classes=(f"{BF}Text",),  # a new optional class
            label="Renamed",
            resource_id="test:renamed",
        )
    )
    graph = record('<https://bcld.info/works/w1> a bf:Work ; bf:note "a", "b" .')

    assert breaking(old, new) == set()
    kinds = {c.kind for c in template_changes(old, new, NONE)}
    assert {"label_changed", "resource_id_changed", "property_added"} <= kinds
    assert {"class_added", "defaults_changed"} <= kinds
    assert reasons(old, new, graph) == []


def test_reordering_properties_is_no_change():
    old = parse(template(WORK, NOTE, DATE))
    new = parse(template(WORK, DATE, NOTE))

    assert template_changes(old, new, NONE) == []


def test_breaking_change_no_record_uses():
    old = parse(template(WORK, NOTE, DATE))
    new = parse(template(WORK, NOTE))
    graph = record('<https://bcld.info/works/w1> a bf:Work ; bf:note "a" .')

    assert breaking(old, new) == {"property_removed"}
    assert reasons(old, new, graph) == []


# --- breaking changes, one per row of #339's table ------------------------------


def test_class_removed():
    old = parse(template(WORK))
    new = parse(template(f"{BF}Text"))
    graph = record("<https://bcld.info/works/w1> a bf:Work .")

    assert breaking(old, new) == {"class_removed", "required_class_changed"}
    assert reasons(old, new, graph) == [f"class {WORK} is no longer in the template"]


def test_property_removed():
    old = parse(template(WORK, NOTE, DATE))
    new = parse(template(WORK, DATE))
    graph = record('<https://bcld.info/works/w1> a bf:Work ; bf:note "a" .')

    assert reasons(old, new, graph) == [
        "property removed; its data would become unused RDF"
    ]


def test_one_of_a_propertys_uris_removed():
    old = parse(template(WORK, Prop(f"{BF}note", more_uris=(f"{BF}summary",))))
    new = parse(template(WORK, Prop(f"{BF}note")))
    graph = record('<https://bcld.info/works/w1> bf:summary "a" .')

    assert breaking(old, new) == {"property_removed"}
    assert reasons(old, new, graph) == [
        "property removed; its data would become unused RDF"
    ]


def test_ordered_changed():
    old = parse(template(WORK, Prop(f"{BF}note", repeatable=True)))
    new = parse(template(WORK, Prop(f"{BF}note", repeatable=True, ordered=True)))
    graph = record('<https://bcld.info/works/w1> bf:note "a", "b" .')

    assert reasons(old, new, graph) == ["ordered flag changed"]


def test_ordered_values_are_read_through_the_list():
    ordered = Prop(f"{BF}note", repeatable=True, ordered=True)
    old = parse(template(WORK, ordered))
    new = parse(template(WORK, Prop(f"{BF}note", ordered=True)))
    graph = record('<https://bcld.info/works/w1> bf:note ( "a" "b" ) .')

    assert reasons(old, new, graph) == [
        "no longer repeatable, but it has more than one value"
    ]


def test_type_changed():
    old = parse(template(WORK, DATE))
    new = parse(template(WORK, Prop(f"{BF}date", "uri")))
    graph = record('<https://bcld.info/works/w1> bf:date "2020" .')

    assert breaking(old, new) == {"type_changed"}
    assert reasons(old, new, graph) == ["property type literal -> uri"]


def test_datatype_added():
    old = parse(template(WORK, DATE))
    new = parse(template(WORK, Prop(f"{BF}date", datatype=XSD_DATE)))

    assert reasons(old, new, record('<https://bcld.info/works/w1> bf:date "2020" .'))
    typed = record('<https://bcld.info/works/w1> bf:date "2020-01-01"^^xsd:date .')
    assert reasons(old, new, typed) == []


def test_regex_tightened():
    old = parse(template(WORK, DATE))
    new = parse(template(WORK, Prop(f"{BF}date", regex="\\d{4}")))

    assert reasons(old, new, record('<https://bcld.info/works/w1> bf:date "n.d." .'))
    # a search, like new RegExp(r).test(v), so it need not match the whole value
    circa = record('<https://bcld.info/works/w1> bf:date "ca. 1990" .')
    assert reasons(old, new, circa) == []


def test_regex_python_cannot_read_is_unknown_not_broken():
    old = parse(template(WORK, DATE))
    new = parse(template(WORK, Prop(f"{BF}date", regex="^\\p{L}+$")))
    graph = record('<https://bcld.info/works/w1> bf:date "1990" .')

    assert reasons(old, new, graph) == []


def test_newly_required():
    old = parse(template(WORK, NOTE, DATE))
    new = parse(template(WORK, NOTE, Prop(f"{BF}date", required=True)))

    without = record('<https://bcld.info/works/w1> bf:note "a" .')
    assert reasons(old, new, without) == ["newly required, but it has no value"]
    with_date = record('<https://bcld.info/works/w1> bf:date "1990" .')
    assert reasons(old, new, with_date) == []


def test_no_longer_repeatable():
    old = parse(template(WORK, NOTE))
    new = parse(template(WORK, Prop(f"{BF}note")))

    two = record('<https://bcld.info/works/w1> bf:note "a", "b" .')
    assert reasons(old, new, two) == [
        "no longer repeatable, but it has more than one value"
    ]
    one = record('<https://bcld.info/works/w1> bf:note "a" .')
    assert reasons(old, new, one) == []


# --- nested templates -------------------------------------------------------------

TITLE = f"{BF}Title"
MAIN_TITLE = Prop(f"{BF}mainTitle")
SUBTITLE = Prop(f"{BF}subtitle")
TITLE_V1 = parse(template(TITLE, MAIN_TITLE, SUBTITLE))
TITLE_V2 = parse(template(TITLE, MAIN_TITLE, SUBTITLE, label="Relabeled"))
TITLE_V3 = parse(template(TITLE, MAIN_TITLE))
NESTED = lookup(
    **{
        version(1, 1): TITLE_V1,
        version(1, 2): TITLE_V2,
        version(1, 3): TITLE_V3,
        version(2, 1): parse(template(TITLE, MAIN_TITLE)),
        version(3, 1): parse(template(TITLE, MAIN_TITLE, suppressible=True)),
    }
)
WITH_TITLE = """
<https://bcld.info/works/w1> a bf:Work ; bf:title _:t .
_:t a bf:Title ; bf:mainTitle "Main" ; bf:subtitle "Sub" .
"""


def titled(ref: str):
    return parse(template(WORK, Prop(f"{BF}title", "resource", nested=(ref,))))


def test_compatible_nested_version_bump():
    old, new = titled(version(1, 1)), titled(version(1, 2))

    assert breaking(old, new, NESTED) == set()
    assert reasons(old, new, record(WITH_TITLE), NESTED) == []


def test_incompatible_nested_version_bump():
    old, new = titled(version(1, 1)), titled(version(1, 3))

    assert breaking(old, new, NESTED) == {"nested_version_changed"}
    problems = breaking_changes(old, new, record(WITH_TITLE), RECORD, NESTED)
    assert [(p.property, p.reason) for p in problems] == [
        (f"{BF}subtitle", "property removed; its data would become unused RDF")
    ]
    assert problems[0].subject != str(RECORD)  # it is on the nested title


def test_nested_template_swapped_to_another_profile():
    old, new = titled(version(1, 1)), titled(version(2, 1))

    assert breaking(old, new, NESTED) == {"nested_removed"}
    assert reasons(old, new, record(WITH_TITLE), NESTED) == [
        f"nested template changed from {version(1, 1)} to {version(2, 1)}"
    ]


def test_nested_template_removed():
    old = titled(version(1, 1))
    new = parse(template(WORK, Prop(f"{BF}title", "resource", nested=())))

    assert reasons(old, new, record(WITH_TITLE), NESTED) == [
        f"no nested template matches it any more (was {version(1, 1)})"
    ]


def test_nested_suppressible_flag_changed():
    old = titled(version(1, 1))
    new = parse(template(WORK, Prop(f"{BF}title", "resource", nested=(version(1, 4),))))
    nested = lookup(
        **{
            version(1, 1): TITLE_V1,
            version(1, 4): parse(template(TITLE, MAIN_TITLE, suppressible=True)),
        }
    )

    assert breaking(old, new, nested) == {"nested_version_changed"}
    assert reasons(old, new, record(WITH_TITLE), nested) == [
        "nested suppressible flag changed"
    ]


MISSING = version(1, 9)


def test_nested_bump_to_a_version_that_cant_be_loaded():
    old, new = titled(version(1, 1)), titled(MISSING)

    [bump] = [
        c
        for c in template_changes(old, new, nested_templates=NESTED)
        if c.kind == "nested_version_changed"
    ]
    assert bump.breaking
    assert f"could not load {MISSING} to compare" in bump.detail
    assert reasons(old, new, record(WITH_TITLE), NESTED) == [
        f"could not load nested template {MISSING} to check it against"
    ]


def test_template_cache_lists_what_it_could_not_load():
    cache = TemplateCache(db=None)  # ty: ignore[invalid-argument-type]
    cache._load = lambda ref: NESTED(ref)  # ty: ignore[invalid-assignment]

    for ref in (version(1, 1), MISSING, "pcc:bf2:Title", MISSING):
        cache(ref)

    assert cache.unresolved() == sorted([MISSING, "pcc:bf2:Title"])


def test_nested_profiles_parsed_once_per_reference():
    calls = []

    def counting(ref):
        calls.append(ref)
        return NESTED(ref)

    old, new = titled(version(1, 1)), titled(version(1, 3))
    graph = record(
        WITH_TITLE
        + '<https://bcld.info/works/w1> bf:title _:u . _:u a bf:Title ; bf:mainTitle "M" .'
    )
    cached = TemplateCache(db=None)  # ty: ignore[invalid-argument-type]
    cached._load = counting  # ty: ignore[invalid-assignment]
    breaking_changes(old, new, graph, RECORD, cached)
    template_changes(old, new, cached)

    assert sorted(calls) == [version(1, 1), version(1, 3)]


# --- sinopia_editor#168: suppressible and non-suppressible siblings ---------------

GENRE = f"{BF}GenreForm"
SUPPRESSED = profile_uri(10) + "/version/1"
RICH = profile_uri(11) + "/version/1"
RICH_2 = profile_uri(12) + "/version/1"
SIBLINGS = lookup(
    **{
        SUPPRESSED: parse(template(GENRE, Prop(f"{BF}uri", "uri"), suppressible=True)),
        RICH: parse(template(GENRE, Prop(f"{RDFS}label"), Prop(f"{BF}source", "uri"))),
        RICH_2: parse(template(GENRE, Prop(f"{RDFS}label"))),
    }
)
GENRES = """
<https://bcld.info/works/w1> a bf:Work ;
    bf:genreForm <http://id.loc.gov/authorities/genreForms/gf1>, _:rich,
        <http://id.loc.gov/authorities/genreForms/gf2> .
_:rich a bf:GenreForm ; rdfs:label "Rich" .
<http://id.loc.gov/authorities/genreForms/gf2> a bf:GenreForm .
"""
BARE = URIRef("http://id.loc.gov/authorities/genreForms/gf1")
TYPE_ONLY = URIRef("http://id.loc.gov/authorities/genreForms/gf2")


def genre(*refs: str):
    return parse(template(WORK, Prop(f"{BF}genreForm", "resource", nested=refs)))


def genres() -> Graph:
    return record("@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n" + GENRES)


def rich_genre(graph: Graph):
    """The blank-node genre, the one described locally."""
    genre_forms = graph.objects(RECORD, URIRef(f"{BF}genreForm"))
    return next(o for o in genre_forms if not isinstance(o, URIRef))


def test_select_nested_prefers_the_non_suppressible_sibling():
    graph = genres()

    match = select_nested(graph, rich_genre(graph), (SUPPRESSED, RICH), SIBLINGS)

    assert isinstance(match, Match)
    assert (match.ref, match.suppressed) == (RICH, False)


def test_select_nested_sends_a_bare_uri_to_the_suppressible_sibling():
    match = select_nested(genres(), BARE, (SUPPRESSED, RICH), SIBLINGS)

    assert isinstance(match, Match)
    assert (match.ref, match.suppressed) == (SUPPRESSED, True)


def test_select_nested_falls_back_for_a_type_only_uri():
    match = select_nested(genres(), TYPE_ONLY, (SUPPRESSED, RICH), SIBLINGS)

    assert isinstance(match, Match)
    assert (match.ref, match.suppressed) == (SUPPRESSED, True)


def test_select_nested_two_non_suppressible_siblings_is_ambiguous():
    graph = genres()

    assert (
        select_nested(graph, rich_genre(graph), (RICH, RICH_2), SIBLINGS) is AMBIGUOUS
    )


def test_siblings_sharing_a_class_are_not_a_change():
    old = genre(SUPPRESSED, RICH)

    assert template_changes(old, genre(RICH, SUPPRESSED), SIBLINGS) == []
    assert reasons(old, genre(SUPPRESSED, RICH), genres(), SIBLINGS) == []


def test_removing_the_suppressible_sibling():
    old, new = genre(SUPPRESSED, RICH), genre(RICH)

    assert breaking(old, new, SIBLINGS) == {"nested_removed"}
    problems = breaking_changes(old, new, genres(), RECORD, SIBLINGS)
    # The bare URI has nothing to go to. The type-only URI falls back to the rich
    # template, which changes the shape it is written in.
    assert {(p.subject, p.reason) for p in problems} == {
        (str(BARE), f"no nested template matches it any more (was {SUPPRESSED})"),
        (str(TYPE_ONLY), f"nested template changed from {SUPPRESSED} to {RICH}"),
    }


def test_adding_a_second_non_suppressible_sibling():
    old, new = genre(SUPPRESSED, RICH), genre(SUPPRESSED, RICH, RICH_2)

    assert breaking(old, new, SIBLINGS) == {"nested_ambiguous"}
    graph = genres()
    problems = breaking_changes(old, new, graph, RECORD, SIBLINGS)
    # Both values with a type now match two non-suppressible templates. The bare
    # URI still goes to the suppressible one.
    assert {(p.subject, p.reason) for p in problems} == {
        (str(subject), "more than one nested template would match it")
        for subject in (TYPE_ONLY, rich_genre(graph))
    }


def test_property_templates_sharing_a_predicate():
    """Two nested-resource property templates may share a predicate when their
    nested classes differ; each value is checked against the one it matches."""
    note_v1 = profile_uri(20) + "/version/1"
    note_v2 = profile_uri(20) + "/version/2"
    title_ref = version(1, 1)
    nested = lookup(
        **{
            title_ref: TITLE_V1,
            note_v1: parse(template(f"{BF}Note", Prop(f"{RDFS}label"), DATE)),
            note_v2: parse(template(f"{BF}Note", Prop(f"{RDFS}label"))),
        }
    )
    shared = f"{BF}relatedTo"
    old = parse(
        template(
            WORK,
            Prop(shared, "resource", nested=(title_ref,)),
            Prop(shared, "resource", nested=(note_v1,)),
        )
    )
    new = parse(
        template(
            WORK,
            Prop(shared, "resource", nested=(note_v2,)),
            Prop(shared, "resource", nested=(title_ref,)),
        )
    )
    graph = record(
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
        "<https://bcld.info/works/w1> bf:relatedTo _:t, _:n .\n"
        '_:t a bf:Title ; bf:mainTitle "Main" .\n'
        '_:n a bf:Note ; rdfs:label "A note" ; bf:date "1990" .\n'
    )

    assert len(old.properties[shared]) == 2
    assert breaking(old, new, nested) == {"nested_version_changed"}
    problems = breaking_changes(old, new, graph, RECORD, nested)
    assert [(p.property, p.reason) for p in problems] == [
        (f"{BF}date", "property removed; its data would become unused RDF")
    ]


# --- one stored record ------------------------------------------------------------

PINNED = version(1, 1)


def stored_record(**literals: str) -> dict:
    """A record's data as it is stored: framed, pinned to PINNED."""
    return {
        "@id": str(RECORD),
        "@type": [WORK],
        "http://sinopia.io/vocabulary/hasResourceTemplate": [{"@id": PINNED}],
        **{f"{BF}{name}": [{"@value": value}] for name, value in literals.items()},
    }


def test_record_problems_reports_breaking_change():
    old = parse(template(WORK, NOTE, DATE))
    new = parse(template(WORK, NOTE))

    problems = record_problems(
        PINNED, stored_record(date="1990"), new, lookup(**{PINNED: old})
    )

    assert problems is not None
    assert [(p.property, p.reason) for p in problems] == [
        (f"{BF}date", "property removed; its data would become unused RDF")
    ]


def test_record_problems_none_for_unresolved_version():
    new = parse(template(WORK, NOTE))

    assert record_problems(PINNED, stored_record(date="1990"), new, NONE) is None


def test_record_problems_none_for_unreadable_data():
    old = parse(template(WORK, NOTE, DATE))

    problems = record_problems(PINNED, {"@context": 5}, old, lookup(**{PINNED: old}))

    assert problems is None


def test_record_problems_empty_when_compatible():
    old = parse(template(WORK, NOTE, DATE))
    new = parse(template(WORK, NOTE, DATE, label="Renamed"))

    problems = record_problems(
        PINNED, stored_record(date="1990"), new, lookup(**{PINNED: old})
    )

    assert problems == []
