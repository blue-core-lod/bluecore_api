"""A stored record read into its bibframe-json model.

The one place the view layer parses `resource.data`. Everything downstream of
it holds a model rather than an untyped dict.
"""

import logging

from bluecore_models.models import Hub, Instance, Work
from bluecore_models.utils.graph import framed_for_storage
from pydantic import ValidationError
from pyld.jsonld import JsonLdError

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

    When new versions of bibframe-json are released, the data is updated to the
    latest version using the reframe bluecore-workflows DAG. However, since this
    process can take hours to complete we need to still be able to display data
    that uses older versions of the bibframe-json context. To achieve this a
    record with an older bibframe-json context is first reframed using the latest
    bibframe-json context, and then read into the relevant Pydantic model.

    A record naming a context that framing cannot read, such as one
    bibframe-json does not yet ship, is read as it was stored, and marked
    `read_as_stored` so the page can say so. Its terms are taken to mean what they
    mean in the current context, which they mostly will, and a page saying it may
    be wrong is more use to a reader than one showing nothing.

    None is only returned when the stored data is not a JSON object: a JSON
    array (such as a list of nodes that was never framed), a string, a number,
    or null. A JSON object always reads, since every field has a default and
    whatever will not read is left out; the last check below is only a safety
    net, logged if it is ever reached.
    """
    data = normalize_context(data)
    if not isinstance(data, dict):
        return None
    context = data.get("@context")
    as_stored = False
    if context != bibframe.CURRENT_CONTEXT:
        try:
            data = framed_for_storage(uri, data)
        except JsonLdError:
            logger.warning(
                "%s names context %r, which will not frame, so it is read as stored",
                uri,
                context,
            )
            as_stored = True
        else:
            logger.info("%s names context %r, so it is framed to read", uri, context)
    resource = _validate(model, data, uri)
    if resource is not None:
        resource._read_as_stored = as_stored
    return resource


def _validate(
    model: type[bibframe.Resource], data: dict, uri: str
) -> bibframe.Resource | None:
    """`data` read into `model`, less any property that will not read."""
    try:
        return model.model_validate(data)
    except ValidationError as error:
        unreadable = _unreadable(error)
    logger.warning(
        "%s: leaving out %s, which will not read",
        uri,
        ", ".join(f"{key}[{i}]" if i is not None else key for key, i in unreadable),
    )
    try:
        return model.model_validate(_without(data, unreadable))
    except ValidationError:
        logger.exception("%s will not read into bibframe-json", uri)
        return None


def _unreadable(error: ValidationError) -> list[tuple[str, int | None]]:
    """Where validation failed, as (property, item): the item of a list that
    failed, or None when the property as a whole did."""
    found: dict[tuple[str, int | None], None] = {}
    for e in error.errors():
        loc = e["loc"]
        if not loc:
            continue
        item = loc[1] if len(loc) > 1 and isinstance(loc[1], int) else None
        found[(str(loc[0]), item)] = None
    return list(found)


def _without(data: dict, unreadable: list[tuple[str, int | None]]) -> dict:
    """The record with what failed taken out: the bad items of a list, so the
    rest of that property still reads, or the whole property otherwise."""
    whole = {key for key, item in unreadable if item is None}
    items: dict[str, set[int]] = {}
    for key, item in unreadable:
        if item is not None:
            items.setdefault(key, set()).add(item)
    kept: dict = {}
    for key, held in data.items():
        if key in whole:
            continue
        if key in items and isinstance(held, list):
            held = [v for i, v in enumerate(held) if i not in items[key]]
        kept[key] = held
    return kept
