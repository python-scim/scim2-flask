import pytest

from examples.minimal_server import InMemoryStorage
from examples.minimal_server import create_provider


@pytest.fixture(autouse=True)
def tutorial_server(doctest_namespace):
    """Expose the storage and the provider of the tutorial to the doctests of the pages."""
    doctest_namespace["InMemoryStorage"] = InMemoryStorage
    doctest_namespace["create_provider"] = create_provider
