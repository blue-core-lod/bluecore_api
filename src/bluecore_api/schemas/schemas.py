from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from bluecore_api.constants import BluecoreType


class ErrorResponse(BaseModel):
    title: str
    details: str | None = None
    status: str


class ResourceBaseSchema(BaseModel):
    id: int | None
    type: str
    data: dict[str, object]
    uri: str | None
    uuid: UUID | None
    created_at: datetime | None
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class InstanceCreateSchema(BaseModel):
    work_id: int | None = None
    data: str


class InstanceSchema(ResourceBaseSchema):
    type: str = BluecoreType.INSTANCES
    work_id: int | None
    is_expanded: bool = False


class InstanceUpdateSchema(BaseModel):
    data: str | None = None
    work_id: int | None = None


class OtherResourceSchema(BaseModel):
    id: int
    data: dict[str, object] | list[object]
    uri: str | None = None


class OtherResourceCreateSchema(BaseModel):
    data: str
    uri: str | None = None


class OtherResourceUpdateSchema(BaseModel):
    data: str | None = None
    uri: str | None = None


class ProfileSchema(BaseModel):
    id: int
    uuid: UUID | None = None
    uri: str | None = None
    data: dict[str, object] | list[object]
    # The URI of the Version this response shows, {uri}/version/{version_id}:
    # the newest one, except from GET /profiles/{uuid}/version/{id}. None only
    # if no version was written.
    version_uri: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ProfileCreateSchema(BaseModel):
    data: str


class ProfileUpdateSchema(BaseModel):
    data: str | None = None


class ProfileValidateSchema(BaseModel):
    # A proposed change to check before it is saved. Without it, the stored
    # profile is reported on.
    data: str | None = None


class ProfileVersionUsageSchema(BaseModel):
    # None for records that name a plain profile URI rather than a version.
    version_uri: str | None
    instance_count: int


class ProfileInstanceSchema(BaseModel):
    uri: str
    version_uri: str | None


class ProfileChangeSchema(BaseModel):
    # e.g. property_removed, nested_version_changed, label_changed
    kind: str
    # The property URI, or None for a change to the template itself.
    property: str | None
    detail: str
    # Whether the change could break a record. Whether one actually breaks is
    # reported in incompatible_instances.
    breaking: bool


class InstanceProblemSchema(BaseModel):
    # The node in the record the problem is on: the record, or a nested resource.
    subject: str
    property: str | None
    reason: str


class IncompatibleInstanceSchema(BaseModel):
    uri: str
    # The version the record is pinned to, which it would stay attached to.
    version_uri: str
    problems: list[InstanceProblemSchema]


class ProfileValidationSchema(BaseModel):
    """What a profile is used by, and whether a proposed change would break it.

    Records are found by the template pointer they carry, so for a nested
    profile versions and instances name the profiles that nest it.

    changes, incompatible_instances and requires_new_version are filled only
    when data is sent. changes compares the stored profile with data.
    incompatible_instances checks each record pinned to a version of this
    profile (not of one that nests it) against data, and is not paged.
    requires_new_version is true when any record could not move to data.
    unresolved_templates lists the nested or pinned template references the
    checks could not load (not stored, or a bare template id); anything they
    affect is reported as breaking rather than assumed safe. If the stored
    profile itself can't be read, it is listed there and changes is empty.
    unchecked_instances lists records that could not be checked at all, because
    their data or the version they are pinned to could not be read; they do not
    count towards requires_new_version.
    """

    profile_uuid: UUID
    profile_uri: str
    current_version_uri: str | None
    instance_count: int
    versions: list[ProfileVersionUsageSchema]
    instances: list[ProfileInstanceSchema]
    requires_new_version: bool = False
    changes: list[ProfileChangeSchema] = []
    incompatible_instances: list[IncompatibleInstanceSchema] = []
    unchecked_instances: list[str] = []
    unresolved_templates: list[str] = []


class HubCreateSchema(BaseModel):
    data: str


class HubSchema(ResourceBaseSchema):
    type: str = BluecoreType.HUBS
    is_expanded: bool = False


class HubUpdateSchema(BaseModel):
    data: str | None = None
    hub_id: int | None = None


class WorkCreateSchema(BaseModel):
    hub_id: int | None = None
    data: str


class WorkUpdateSchema(BaseModel):
    data: str | None = None


class WorkSchema(ResourceBaseSchema):
    type: str = BluecoreType.WORKS
    hub_id: int | None
    is_expanded: bool = False


class BatchCreateSchema(BaseModel):
    uri: str | None = None


class BatchSchema(BaseModel):
    uri: str | None = None
    workflow_id: str


class LinksSchema(BaseModel):
    first: str
    prev: str | None = None
    next: str | None = None


class SearchResultSchema(BaseModel):
    results: Sequence[ResourceBaseSchema]
    links: LinksSchema
    total: int


class SearchProfileResultSchema(BaseModel):
    results: Sequence[ProfileSchema]
    links: LinksSchema
    total: int


class HealthSchema(BaseModel):
    status: str
    version: str


class ExportSchema(BaseModel):
    instance_uri: str
    local_id: str | None = None


class ExportResponseSchema(BaseModel):
    instance_uri: str
    local_id: str | None = None
    workflow_id: str


class VersionSchema(BaseModel):
    id: int
    timestamp: str
    # Always set: version_list() falls back through keycloak_user_id to
    # "unknown" rather than emitting a null the editor would render verbatim.
    user: str


class VersionListSchema(BaseModel):
    versions: Sequence[VersionSchema]
