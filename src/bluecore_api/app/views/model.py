"""A stored record read into its bibframe-json model.

The one place the view layer parses `resource.data`. Everything downstream of
it holds a model rather than an untyped dict.
"""

import logging

from bluecore_models.models import Hub, Instance, Work
from pydantic import ValidationError

from bluecore_api.app.utils.jsonld import model_data_as_dict, normalize_context
from bluecore_api.schemas import bibframe

logger = logging.getLogger(__name__)

# Which model a row reads into, by the class the row already is. Not by @type:
# a Blue Core Hub is typed both bf:Work and bf:Hub, which the ORM has settled.
MODELS: dict[type, type[bibframe.Resource]] = {
    Hub: bibframe.Hub,
    Instance: bibframe.Instance,
    Work: bibframe.Work,
}


def as_model(record: Hub | Instance | Work) -> bibframe.Resource | None:
    """The record as a Work, Instance or Hub, or None if it is not one these
    read; see `read`."""
    model = MODELS.get(type(record))
    if model is None:
        return None
    return read(model, model_data_as_dict(record.data), record.uri)


def read(
    model: type[bibframe.Resource], data: object, uri: str
) -> bibframe.Resource | None:
    """Stored data read into `model`, or None if it is not a record these read.

    A property that will not read is left out, and the rest of the record
    still reads, so one malformed property costs the page that field and no
    other. The log names what was left out.

    None only for data that is no record at all, or that names a bibframe-json
    version other than the one these models read. The reframe DAG keeps
    stored rows on the current version, so one that is not was missed by a
    backfill, and guessing at what its terms mean would be worse than showing
    nothing.
    """
    data = normalize_context(data)
    if not isinstance(data, dict):
        return None
    context = data.get("@context")
    if context != bibframe.CURRENT_CONTEXT:
        logger.warning("%s names context %r, not the current one", uri, context)
        return None
    try:
        return model.model_validate(data)
    except ValidationError as error:
        unreadable = sorted({str(e["loc"][0]) for e in error.errors() if e["loc"]})
    logger.warning(
        "%s: leaving out %s, which will not read", uri, ", ".join(unreadable)
    )
    try:
        return model.model_validate(
            {k: v for k, v in data.items() if k not in unreadable}
        )
    except ValidationError:
        logger.exception("%s will not read into bibframe-json", uri)
        return None
