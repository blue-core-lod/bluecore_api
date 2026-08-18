"""Renders the HTML page for a Hub, Work or Instance.

One entry point per type: main column from `fields`, sidebar from `sidebar`.
"""

from typing import Any

from bluecore_models.models import Hub, Instance, Work
from fastapi import Request, Response

from bluecore_api.app.views.fields import (
    IMPLIED_HUB_TYPES,
    IMPLIED_WORK_TYPES,
    _build_fields,
    _extra_types,
    _insert_type_field,
    _is_stub,
    _mark_bulleted,
    _node_values,
)
from bluecore_api.app.views.sidebar import (
    _add_section,
    _record_link,
    relation_sections,
    works_for_hub,
)
from bluecore_api.app.views.templating import templates
from bluecore_api.app.views.values import (
    _dedupe,
    _title_of,
)
from bluecore_api.app.views.vocabulary import (
    _build_label_map,
)


def render_instance_html(instance: Instance, request: Request) -> Response:
    data = instance.data
    label_map = _build_label_map(instance)
    fields = _build_fields(data, label_map)
    _mark_bulleted(fields)

    sidebar: list[dict[str, Any]] = []
    work = instance.work
    if work is not None:
        sidebar.append({"label": "Instance of", "values": [_record_link(work)]})
    elif "instanceOf" in data:
        sidebar.append(
            {
                "label": "Instance of",
                "values": _node_values(data["instanceOf"], label_map),
            }
        )

    return templates.TemplateResponse(
        request,
        "resource.html",
        {
            "doc_type": "BIBFRAME Instance",
            "title": _title_of(data),
            "fields": fields,
            "sidebar": sidebar,
            "resource_uri": instance.uri,
            "is_work": False,
            "is_hub": False,
            "is_stub": _is_stub(data),
        },
    )


def render_work_html(work: Work, request: Request) -> Response:
    data = work.data
    label_map = _build_label_map(work)
    fields = _build_fields(data, label_map)
    _insert_type_field(fields, _extra_types(data, IMPLIED_WORK_TYPES))
    _mark_bulleted(fields)

    sidebar: list[dict[str, Any]] = []
    instance_values = [_record_link(inst) for inst in work.instances]
    if instance_values:
        _add_section(sidebar, "Has Instance", instance_values)
    for section in relation_sections(work, label_map):
        _add_section(sidebar, section["label"], section["values"])
    if "seriesStatement" in data:
        # merges with the Series heading a bf:relation may already have opened,
        # rather than showing the reader the same heading twice
        _add_section(
            sidebar, "Series", _node_values(data["seriesStatement"], label_map)
        )

    return templates.TemplateResponse(
        request,
        "resource.html",
        {
            "doc_type": "BIBFRAME Work",
            "title": _title_of(data),
            "fields": fields,
            "sidebar": sidebar,
            "resource_uri": work.uri,
            "is_work": True,
            "is_hub": False,
            "is_stub": _is_stub(data),
        },
    )


def render_hub_html(hub: Hub, request: Request) -> Response:
    data = hub.data
    label_map = _build_label_map(hub)
    fields = _build_fields(data, label_map)
    _insert_type_field(fields, _extra_types(data, IMPLIED_HUB_TYPES))
    _mark_bulleted(fields)

    sidebar: list[dict[str, Any]] = []
    for section in relation_sections(hub, label_map):
        _add_section(sidebar, section["label"], section["values"])

    # A described Hub names its Works above, so this catches only the ones just
    # the Work end asserts, without repeating anything already linked.
    linked = {
        value["href"]
        for section in sidebar
        for value in section["values"]
        if value["href"]
    }
    work_values = _dedupe(
        [_record_link(work) for work in works_for_hub(hub) if work.uri not in linked]
    )
    if work_values:
        _add_section(sidebar, "Associated Works", work_values)

    return templates.TemplateResponse(
        request,
        "resource.html",
        {
            "doc_type": "BIBFRAME Hub",
            "title": _title_of(data),
            "fields": fields,
            "sidebar": sidebar,
            "resource_uri": hub.uri,
            "is_work": False,
            "is_hub": True,
            "is_stub": _is_stub(data),
        },
    )
