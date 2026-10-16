import pytest
from bluecore_models.models import Hub, Instance, Work

from bluecore_api.app.views import model
from bluecore_api.schemas import bibframe

UUID = "00000000-0000-4000-8000-000000000000"
PATHS = {Hub: "hubs", Instance: "instances", Work: "works"}


@pytest.fixture
def stored():
    """A record as the page reads it: stored, then read into its model.

    Goes through the ORM's write path, which frames whatever it is handed into
    the shape bibframe-json describes -- so a test can write a property as a
    bare value, the way a person would, and still get the list a stored record
    holds.
    """

    def store(of=Work, **properties) -> bibframe.Resource:
        """A record of class `of`, a Work unless it says otherwise."""
        uri = f"https://bcld.info/{PATHS[of]}/{UUID}"
        record = of(uri=uri, data={"@id": uri, "@type": of.__name__, **properties})
        resource = model.as_model(record)
        assert resource is not None, "the framed record would not read"
        return resource

    return store
