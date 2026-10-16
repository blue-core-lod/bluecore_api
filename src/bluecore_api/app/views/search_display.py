"""Search display logic for main search page
this will be fleshed out for more search view additions in the future
"""

from bluecore_models.models import Hub, Instance, Work

from bluecore_api.app.views import fields, model, nodes


def resource_title(resource: Hub | Instance | Work) -> str:
    """A display title for a Hub, Work or Instance: the page's own heading.

    A record the models will not read at all is named by its uuid, as its
    own page is.
    """
    read = model.as_model(resource)
    return fields.title_of(read) if read is not None else nodes.id_tail(resource.uri)
