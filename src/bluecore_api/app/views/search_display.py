"""Search display logic for main search page
   this will be fleshed out for more search view additions in the future
"""

from bluecore_models.models import Hub, Instance, Work

from bluecore_api.app.views import nodes


def resource_title(resource: Hub | Instance | Work) -> str:
    """A display title for a Hub, Work or Instance."""
    return nodes.title_of(resource.data)