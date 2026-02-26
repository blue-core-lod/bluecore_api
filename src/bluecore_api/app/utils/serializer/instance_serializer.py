from typing import Callable

from fastapi import Request, Response

from bluecore_api.app.utils.serializer.cbd import (
    generate_cbd_jsonld_response,
    generate_cbd_xml_response,
)
from bluecore_models.models import Instance

type InstanceSerializerFn = Callable[[Instance], Response]
instance_serializer_format_registry: dict[str, InstanceSerializerFn] = {
    "cbdjsonld": generate_cbd_jsonld_response,
    "cbdxml": generate_cbd_xml_response,
}
instance_serializer_accept_registry: dict[str, InstanceSerializerFn] = {
    "application/cbd+jsonld": generate_cbd_jsonld_response,
    "application/cbd+xml": generate_cbd_xml_response,
}


def serialize_instance(
    instance: Instance, format: str | None, request: Request
) -> Response | None:
    if format in instance_serializer_format_registry:
        return instance_serializer_format_registry[format](instance)
    accept_header = request.headers.get("accept", "")
    for accept in accept_header.split(","):
        accept = accept.strip()
        if accept in instance_serializer_accept_registry:
            return instance_serializer_accept_registry[accept](instance)
    return None
