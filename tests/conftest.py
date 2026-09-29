from collections.abc import Callable

import pytest
from flask import Flask
from scim2_client.engines.werkzeug import TestSCIMClient
from werkzeug.test import Client

from examples.minimal_server import create_app


@pytest.fixture
def app() -> Flask:
    return create_app()


@pytest.fixture
def client(app: Flask) -> Client:
    return Client(app)


@pytest.fixture
def make_scim_client() -> Callable[[Flask], TestSCIMClient]:
    """Build a SCIM client for an app a test sets up with its own storage."""

    def make(app: Flask) -> TestSCIMClient:
        return TestSCIMClient(
            Client(app),
            scim_prefix="/scim/v2",
            provider=app.extensions["scim2"].provider,
        )

    return make


@pytest.fixture
def scim_client(app: Flask, make_scim_client) -> TestSCIMClient:
    return make_scim_client(app)
