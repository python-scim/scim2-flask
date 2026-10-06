import pytest
from flask import Flask
from flask import request
from flask import url_for
from scim2_models import AuthenticationScheme
from scim2_models import Bulk
from scim2_models import ETag
from scim2_models import Filter
from scim2_models import ResourceType
from scim2_models import ScimProvider
from scim2_models import ServiceProviderConfig
from scim2_models import UnauthorizedException
from scim2_models import User
from scim2_server.memory import InMemoryStorage
from scim2_server.service import ScimService
from werkzeug.datastructures import WWWAuthenticate
from werkzeug.exceptions import Unauthorized
from werkzeug.test import Client

from scim2_flask import ScimServer

SCIM_JSON = "application/scim+json"
USER = {"schemas": [User.__schema__], "userName": "bjensen"}
BULK_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:BulkRequest"


def create_provider(config: ServiceProviderConfig | None = None) -> ScimProvider:
    return ScimProvider(
        models=[User],
        resource_types=[ResourceType.from_resource(User)],
        config=config,
    )


def create_client(scim_server_class: type[ScimServer] = ScimServer, **kwargs) -> Client:
    app = Flask(__name__)
    kwargs.setdefault("provider", create_provider())
    scim_server_class(InMemoryStorage(), app=app, **kwargs)
    return Client(app)


def bulk_payload(size: int) -> dict:
    """Return a bulk request whose JSON body is at least ``size`` bytes long."""
    return {
        "schemas": [BULK_SCHEMA],
        "Operations": [
            {"method": "DELETE", "path": f"/Users/{'x' * size}"},
        ],
    }


def test_requires_at_least_one_resource_type():
    with pytest.raises(ValueError, match="at least one resource type"):
        ScimServer(InMemoryStorage(), ScimProvider())


def test_init_app_registers_the_extension_later():
    scim_server = ScimServer(InMemoryStorage(), create_provider())
    app = Flask(__name__)
    scim_server.init_app(app)

    assert app.extensions["scim"] == {"scim": scim_server}
    assert Client(app).get("/scim/v2/Users").status_code == 200


def test_endpoints_are_served_under_the_url_prefix():
    client = create_client(url_prefix="/api/scim/")

    created = client.post("/api/scim/Users", json=USER, content_type=SCIM_JSON)
    assert created.status_code == 201
    assert created.json["meta"]["location"] == (
        f"http://localhost/api/scim/Users/{created.json['id']}"
    )
    assert client.get("/api/scim/Users").json["totalResults"] == 1


def test_endpoints_can_be_served_at_the_application_root():
    client = create_client(url_prefix="")

    created = client.post("/Users", json=USER, content_type=SCIM_JSON)
    assert created.json["meta"]["location"] == (
        f"http://localhost/Users/{created.json['id']}"
    )
    assert client.get("/").json["totalResults"] == 1


def test_locations_follow_the_host_and_script_name():
    client = create_client()

    created = client.post(
        "/scim/v2/Users",
        json=USER,
        content_type=SCIM_JSON,
        base_url="https://scim.example.org/app",
    )
    assert created.headers["Location"] == (
        f"https://scim.example.org/app/scim/v2/Users/{created.json['id']}"
    )


def test_several_instances_serve_one_application():
    app = Flask(__name__)
    tenant_a = ScimServer(
        InMemoryStorage(),
        create_provider(),
        app=app,
        url_prefix="/a/scim/v2",
        name="tenant_a",
    )
    tenant_b = ScimServer(
        InMemoryStorage(),
        create_provider(),
        app=app,
        url_prefix="/b/scim/v2",
        name="tenant_b",
    )
    assert app.extensions["scim"] == {"tenant_a": tenant_a, "tenant_b": tenant_b}
    client = Client(app)

    created = client.post("/a/scim/v2/Users", json=USER, content_type=SCIM_JSON)
    assert created.json["meta"]["location"] == (
        f"http://localhost/a/scim/v2/Users/{created.json['id']}"
    )
    assert client.get("/a/scim/v2/Users").json["totalResults"] == 1
    assert client.get("/b/scim/v2/Users").json["totalResults"] == 0


def test_endpoints_are_named_after_the_routes():
    app = Flask(__name__)
    ScimServer(InMemoryStorage(), create_provider(), app=app)

    with app.test_request_context():
        assert url_for("scim.query", resource_endpoint="Users", resource_id="42") == (
            "/scim/v2/Users/42"
        )
        assert url_for("scim.service_provider_config") == (
            "/scim/v2/ServiceProviderConfig"
        )


def test_unknown_path_answers_a_scim_404():
    response = create_client().get("/scim/v2/Users/42/unknown")

    assert response.status_code == 404
    assert response.headers["Content-Type"] == SCIM_JSON
    assert response.json["schemas"] == ["urn:ietf:params:scim:api:messages:2.0:Error"]


@pytest.mark.parametrize(
    ("method", "path", "allowed"),
    [
        ("PUT", "/scim/v2/Users", "GET, POST"),
        ("DELETE", "/scim/v2/", "GET"),
    ],
)
def test_unsupported_method_answers_a_scim_405(method, path, allowed):
    response = create_client().open(path, method=method)

    assert response.status_code == 405
    assert response.headers["Allow"] == allowed
    assert response.headers["Content-Type"] == SCIM_JSON


def test_responses_keep_the_status_headers_and_body_of_the_service():
    client = create_client(
        provider=create_provider(ServiceProviderConfig(etag=ETag(supported=True)))
    )

    created = client.post("/scim/v2/Users", json=USER, content_type=SCIM_JSON)
    assert created.status_code == 201
    assert created.headers["Content-Type"] == SCIM_JSON
    assert created.headers["ETag"] == created.json["meta"]["version"]
    location = created.headers["Location"]

    not_modified = client.get(
        location, headers={"If-None-Match": created.headers["ETag"]}
    )
    assert not_modified.status_code == 304

    deleted = client.delete(location)
    assert deleted.status_code == 204
    assert deleted.data == b""


def test_query_string_is_passed_to_the_service():
    config = ServiceProviderConfig(filter=Filter(supported=True, max_results=10))
    client = create_client(provider=create_provider(config))
    client.post("/scim/v2/Users", json=USER, content_type=SCIM_JSON)
    client.post(
        "/scim/v2/Users",
        json={**USER, "userName": "jsmith"},
        content_type=SCIM_JSON,
    )

    response = client.get(
        "/scim/v2/Users", query_string={"filter": 'userName eq "jsmith"'}
    )
    assert [user["userName"] for user in response.json["Resources"]] == ["jsmith"]


def test_bulk_body_beyond_max_payload_size_is_refused():
    config = ServiceProviderConfig(
        bulk=Bulk(supported=True, max_operations=10, max_payload_size=100)
    )
    client = create_client(provider=create_provider(config))

    response = client.post(
        "/scim/v2/Bulk", json=bulk_payload(200), content_type=SCIM_JSON
    )
    assert response.status_code == 413
    assert response.headers["Content-Type"] == SCIM_JSON


def test_unsupported_bulk_is_refused_whatever_its_max_payload_size():
    config = ServiceProviderConfig(
        bulk=Bulk(supported=False, max_operations=0, max_payload_size=0)
    )
    client = create_client(provider=create_provider(config))

    response = client.post(
        "/scim/v2/Bulk", json=bulk_payload(10), content_type=SCIM_JSON
    )
    assert response.status_code == 501


def test_stricter_application_limit_is_kept_for_bulk_requests():
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 50
    ScimServer(InMemoryStorage(), create_provider(), app=app)

    response = Client(app).post(
        "/scim/v2/Bulk", json=bulk_payload(100), content_type=SCIM_JSON
    )
    assert response.status_code == 413


def test_max_payload_size_only_limits_bulk_requests():
    config = ServiceProviderConfig(
        bulk=Bulk(supported=True, max_operations=10, max_payload_size=10)
    )
    client = create_client(provider=create_provider(config))

    response = client.post("/scim/v2/Users", json=USER, content_type=SCIM_JSON)
    assert response.status_code == 201


def test_scim_exception_raised_by_a_hook_answers_a_scim_error():
    """A hook refusing a request gets the challenges of the announced schemes.

    RFC7644 §2: "a SCIM service provider SHALL indicate supported HTTP
    authentication schemes via the "WWW-Authenticate" header."
    """

    class ProtectedScimServer(ScimServer):
        def create_blueprint(self):
            blueprint = super().create_blueprint()

            @blueprint.before_request
            def refuse():
                raise UnauthorizedException(detail="Missing token")

            return blueprint

    config = ServiceProviderConfig(
        authentication_schemes=[
            AuthenticationScheme(
                type="oauthbearertoken",
                name="OAuth Bearer Token",
                description="Authentication with an OAuth bearer token",
            )
        ]
    )
    client = create_client(ProtectedScimServer, provider=create_provider(config))

    response = client.get("/scim/v2/Users")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"].startswith("Bearer")
    assert response.headers["Content-Type"] == SCIM_JSON
    assert response.json["detail"] == "Missing token"


def test_http_exception_raised_by_a_hook_keeps_its_headers():
    class ProtectedScimServer(ScimServer):
        def create_blueprint(self):
            blueprint = super().create_blueprint()

            @blueprint.before_request
            def refuse():
                raise Unauthorized(
                    "Missing or invalid token",
                    www_authenticate=WWWAuthenticate("Bearer"),
                )

            return blueprint

    response = create_client(ProtectedScimServer).get("/scim/v2/Users")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.headers["Content-Type"] == SCIM_JSON
    assert response.json["detail"] == "Missing or invalid token"


def test_subject_is_passed_to_the_service():
    class HeaderScimServer(ScimServer):
        def get_subject(self):
            return request.headers.get("X-User")

    class MeService(ScimService):
        def me_target(self, request):
            return self.get_resource_type("User"), request.subject

    provider = create_provider()
    client = create_client(
        HeaderScimServer, provider=provider, service=MeService(provider)
    )
    created = client.post("/scim/v2/Users", json=USER, content_type=SCIM_JSON)

    response = client.get("/scim/v2/Me", headers={"X-User": created.json["id"]})
    assert response.status_code == 200
    assert response.json["userName"] == "bjensen"
    assert response.headers["Location"] == created.headers["Location"]


def test_steps_of_the_service_can_be_overridden():
    class PublicService(ScimService):
        def resource_location(self, base_url, resource_type, resource_id):
            return f"https://scim.example.org/v2/Users/{resource_id}"

    provider = create_provider()
    client = create_client(provider=provider, service=PublicService(provider))

    created = client.post("/scim/v2/Users", json=USER, content_type=SCIM_JSON)
    assert created.json["meta"]["location"] == (
        f"https://scim.example.org/v2/Users/{created.json['id']}"
    )


def test_unexpected_exceptions_reach_flask():
    class BrokenStorage(InMemoryStorage):
        def search(self, resource_types, search_request):
            raise RuntimeError("database is down")

    app = Flask(__name__)
    app.testing = True
    ScimServer(BrokenStorage(), create_provider(), app=app)

    with pytest.raises(RuntimeError, match="database is down"):
        Client(app).get("/scim/v2/Users")
