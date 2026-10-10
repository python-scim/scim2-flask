from flask import Flask
from scim2_server.memory import InMemoryStorage
from werkzeug.test import Client

from examples.minimal_server import create_provider
from examples.transactions import TransactionalScimServer

USER = {
    "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
    "userName": "bjensen",
}


class RecordingSession:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def commit(self) -> None:
        self.calls.append("commit")

    def rollback(self) -> None:
        self.calls.append("rollback")


class BrokenStorage(InMemoryStorage):
    def search(self, resource_types, search_request, *, position=None):
        raise RuntimeError("database is down")


def create_client(storage: InMemoryStorage, session: RecordingSession) -> Client:
    app = Flask(__name__)
    TransactionalScimServer(storage, create_provider(), session=session, app=app)
    return Client(app)


def test_successful_request_is_committed():
    session = RecordingSession()
    response = create_client(InMemoryStorage(), session).post(
        "/scim/v2/Users", json=USER
    )

    assert response.status_code == 201
    assert session.calls == ["commit"]


def test_scim_error_is_committed():
    session = RecordingSession()
    response = create_client(InMemoryStorage(), session).get("/scim/v2/Users/unknown")

    assert response.status_code == 404
    assert session.calls == ["commit"]


def test_unexpected_exception_is_rolled_back():
    session = RecordingSession()
    response = create_client(BrokenStorage(), session).get("/scim/v2/Users")

    assert response.status_code == 500
    assert session.calls == ["rollback"]
