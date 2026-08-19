"""Renders the HTML page for a Hub, Work or Instance.

One entry point per type: main column from `fields`, sidebar from `sidebar`.
"""

from typing import Any

from bluecore_models.models import Hub, Instance, Work
from fastapi import Request, Response

from bluecore_api.app.views import (
    fields,
    nodes,
    sidebar,
    templating,
    vocabulary,
)


def render_instance_html(instance: Instance, request: Request) -> Response:
    """Renders one Instance -- a particular published edition of a Work.

    Its sidebar holds a single link, back to the Work it is an instance of.
    """
    data = instance.data
    label_map = vocabulary.build_label_map(instance)
    main_fields = fields.build_fields(data, label_map)
    fields.mark_bulleted(main_fields)

    sidebar_sections: list[dict[str, Any]] = []
    work = instance.work
    if work is not None:
        sidebar_sections.append(
            {"label": "Instance of", "values": [sidebar.record_link(work)]}
        )
    elif "instanceOf" in data:
        sidebar_sections.append(
            {
                "label": "Instance of",
                "values": fields.node_values(data["instanceOf"], label_map),
            }
        )

    return templating.templates.TemplateResponse(
        request,
        "resource.html",
        {
            "doc_type": "BIBFRAME Instance",
            "title": nodes.title_of(data),
            "fields": main_fields,
            "sidebar": sidebar_sections,
            "resource_uri": instance.uri,
            "is_work": False,
            "is_hub": False,
            "is_stub": fields.is_stub(data),
        },
    )


def render_work_html(work: Work, request: Request) -> Response:
    """Renders one Work -- the thing itself, apart from any published edition.

    Its sidebar lists the Instances beneath it and whatever its bf:relation
    points at, such as the Hub for a series.
    """
    data = work.data
    label_map = vocabulary.build_label_map(work)
    main_fields = fields.build_fields(data, label_map)
    fields.insert_type_field(
        main_fields, fields.extra_types(data, fields.IMPLIED_WORK_TYPES)
    )
    fields.mark_bulleted(main_fields)

    sidebar_sections: list[dict[str, Any]] = []
    instance_values = [sidebar.record_link(inst) for inst in work.instances]
    if instance_values:
        sidebar.add_section(sidebar_sections, "Has Instance", instance_values)
    for section in sidebar.relation_sections(work, label_map):
        sidebar.add_section(sidebar_sections, section["label"], section["values"])
    if "seriesStatement" in data:
        # merges with the Series heading a bf:relation may already have opened,
        # rather than showing the reader the same heading twice
        sidebar.add_section(
            sidebar_sections,
            "Series",
            fields.node_values(data["seriesStatement"], label_map),
        )

    return templating.templates.TemplateResponse(
        request,
        "resource.html",
        {
            "doc_type": "BIBFRAME Work",
            "title": nodes.title_of(data),
            "fields": main_fields,
            "sidebar": sidebar_sections,
            "resource_uri": work.uri,
            "is_work": True,
            "is_hub": False,
            "is_stub": fields.is_stub(data),
        },
    )


def render_hub_html(hub: Hub, request: Request) -> Response:
    """Renders one Hub -- the record gathering everything about a single work.

    Its sidebar gets a section per relationship ("Series of", "Translated as"),
    plus any Works that point here without the Hub naming them back.
    """
    data = hub.data
    label_map = vocabulary.build_label_map(hub)
    main_fields = fields.build_fields(data, label_map)
    fields.insert_type_field(
        main_fields, fields.extra_types(data, fields.IMPLIED_HUB_TYPES)
    )
    fields.mark_bulleted(main_fields)

    sidebar_sections: list[dict[str, Any]] = []
    for section in sidebar.relation_sections(hub, label_map):
        sidebar.add_section(sidebar_sections, section["label"], section["values"])

    # A described Hub names its Works above, so this catches only the ones just
    # the Work end asserts, without repeating anything already linked.
    linked = {
        value["href"]
        for section in sidebar_sections
        for value in section["values"]
        if value["href"]
    }
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
            "title": nodes.title_of(data),
            "fields": main_fields,
            "sidebar": sidebar_sections,
            "resource_uri": hub.uri,
            "is_work": False,
            "is_hub": True,
            "is_stub": fields.is_stub(data),
        },
    )
