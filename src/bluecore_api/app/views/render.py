"""Renders the HTML page for a Hub, Work or Instance.

One entry point per type: main column from `fields`, sidebar from `sidebar`.
"""

from bluecore_models.models import Hub, Instance, Work
from fastapi import Request, Response

from bluecore_api.app.views import (
    fields,
    model,
    nodes,
    sidebar,
    templating,
    vocabulary,
)
from bluecore_api.schemas import bibframe


def _main_column(
    record: Hub | Instance | Work, label_map: dict[str, str]
) -> tuple[list[dict[str, object]], str, bibframe.Resource | None]:
    """The fields and the heading of a record's page, and the model they are
    read from, for the sidebar.

    A record the models will not read at all -- stored data that is no JSON
    object, which views/model.py logs -- gets its uuid for a heading and
    nothing else.
    """
    resource = model.as_model(record)
    if resource is None:
        return [], nodes.id_tail(record.uri), None
    return fields.build_fields(resource, label_map), fields.title_of(resource), resource


def render_instance_html(instance: Instance, request: Request) -> Response:
    """Renders one Instance -- a particular published edition of a Work.

    Its sidebar holds a single link, back to the Work it is an instance of.
    """
    label_map = vocabulary.build_label_map(instance)
    main_fields, title, resource = _main_column(instance, label_map)
    fields.mark_bulleted(main_fields)

    sidebar_sections: list[dict[str, object]] = []
    work = instance.work
    if work is not None:
        sidebar_sections.append(
            {"label": "Instance of", "values": [sidebar.record_link(work)]}
        )
    elif isinstance(resource, bibframe.Instance) and resource.instance_of:
        # a Work we do not hold: its uri is all there is, so link to it
        sidebar_sections.append(
            {
                "label": "Instance of",
                "values": [
                    nodes.value(*fields.ref_text(ref, label_map))
                    for ref in resource.instance_of
                ],
            }
        )

    return templating.templates.TemplateResponse(
        request,
        "resource.html",
        {
            "doc_type": "BIBFRAME Instance",
            "title": title,
            "fields": main_fields,
            "read_as_stored": resource is not None and resource.read_as_stored,
            "sidebar": sidebar_sections,
            "resource_uri": instance.uri,
            "is_work": False,
            "is_hub": False,
        },
    )


def render_work_html(work: Work, request: Request) -> Response:
    """Renders one Work -- the thing itself, apart from any published edition.

    Its sidebar lists the Instances beneath it and whatever its bf:relation
    points at, such as the Hub for a series.
    """
    label_map = vocabulary.build_label_map(work)
    main_fields, title, resource = _main_column(work, label_map)
    if resource is not None:
        fields.insert_type_field(
            main_fields, fields.extra_types(resource, fields.IMPLIED_WORK_TYPES)
        )
    fields.mark_bulleted(main_fields)

    sidebar_sections: list[dict[str, object]] = []
    expressed = sidebar.linked_records(work, resource.expression_of if resource else [])
    if expressed:
        sidebar.add_section(sidebar_sections, "Expression Of", expressed)
    instance_values = [sidebar.record_link(inst) for inst in work.instances]
    if instance_values:
        sidebar.add_section(sidebar_sections, "Has Instance", instance_values)
    relations = resource.relation if resource else []
    for section in sidebar.relation_sections(work, relations, label_map):
        sidebar.add_section(sidebar_sections, str(section["label"]), section["values"])  # ty: ignore[invalid-argument-type]
    if resource and resource.series_statement:
        # merges with the Series heading a bf:relation may already have opened,
        # rather than showing the reader the same heading twice
        sidebar.add_section(
            sidebar_sections,
            "Series",
            [nodes.value(str(s)) for s in resource.series_statement],
        )

    return templating.templates.TemplateResponse(
        request,
        "resource.html",
        {
            "doc_type": "BIBFRAME Work",
            "title": title,
            "fields": main_fields,
            "read_as_stored": resource is not None and resource.read_as_stored,
            "sidebar": sidebar_sections,
            "resource_uri": work.uri,
            "is_work": True,
            "is_hub": False,
        },
    )


def render_hub_html(hub: Hub, request: Request) -> Response:
    """Renders one Hub -- the record gathering everything about a single work.

    Its sidebar gets a section per relationship ("Series of", "Translated as"),
    plus any Works that point here without the Hub naming them back.
    """
    label_map = vocabulary.build_label_map(hub)
    main_fields, title, resource = _main_column(hub, label_map)
    if resource is not None:
        fields.insert_type_field(
            main_fields, fields.extra_types(resource, fields.IMPLIED_HUB_TYPES)
        )
    fields.mark_bulleted(main_fields)

    sidebar_sections: list[dict[str, object]] = []
    expressions = sidebar.linked_records(
        hub, resource.has_expression if isinstance(resource, bibframe.Hub) else []
    )
    if expressions:
        sidebar.add_section(sidebar_sections, "Has Expression", expressions)
    relations = resource.relation if resource else []
    for section in sidebar.relation_sections(hub, relations, label_map):
        sidebar.add_section(sidebar_sections, str(section["label"]), section["values"])  # ty: ignore[invalid-argument-type]

    # A described Hub names its Works above, so the foreign key catches only the
    # ones it does not -- a Work ingested after the Hub was described -- without
    # repeating anything already linked.
    linked: set[object] = set()
    for section in sidebar_sections:
        section_values = section["values"]
        if isinstance(section_values, list):
            for val in section_values:
                if isinstance(val, dict) and val.get("href"):
                    linked.add(val["href"])
    work_values = nodes.dedupe(
        [
            sidebar.record_link(work)
            for work in sidebar.works_for_hub(hub)
            if work.uri not in linked
        ]
    )
    if work_values:
        sidebar.add_section(sidebar_sections, "Associated Works", work_values)

    return templating.templates.TemplateResponse(
        request,
        "resource.html",
        {
            "doc_type": "BIBFRAME Hub",
            "title": title,
            "fields": main_fields,
            "read_as_stored": resource is not None and resource.read_as_stored,
            "sidebar": sidebar_sections,
            "resource_uri": hub.uri,
            "is_work": False,
            "is_hub": True,
        },
    )
