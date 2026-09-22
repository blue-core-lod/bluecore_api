"""Wire format for an external record fetched for editing."""

from pydantic import BaseModel, Field


class ExternalResourceSchema(BaseModel):
    """An external BIBFRAME record, framed the way Blue Core serves its own.

    The field names follow the envelope sinopia_editor's fetchResource already
    expects (`data`, `uri`, `type`), so the only client change needed is
    sending an external URI here instead of dereferencing it directly.
    """

    uri: str = Field(
        description=(
            "The URI the source's own graph uses for this record. It can differ "
            "in scheme from the one requested: id.loc.gov publishes http URIs "
            "but redirects browsers to https."
        )
    )
    type: str = Field(description="works, instances or hubs.")
    source: str = Field(description="Host the record came from, e.g. id.loc.gov.")
    data: dict[str, object] = Field(
        description=(
            "The source's own graph, framed around the record and with any "
            "embedded counterpart record reduced to a reference. Not stored."
        )
    )
    bluecore_uri: str | None = Field(
        default=None,
        description=(
            "A Blue Core resource already derived from this record, if there "
            "is one. Null means we hold no copy."
        ),
    )
