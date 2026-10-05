import pytest
from flask import Flask
from scim2_models import EnterpriseUser
from scim2_models import Meta
from scim2_models import MutabilityException
from scim2_models import PatchOp
from scim2_models import PatchOperation
from scim2_models import ResourceType
from scim2_models import Schema
from scim2_models import SCIMException
from scim2_models import ScimPolicy
from scim2_models import ScimProvider
from scim2_models import SearchRequest
from scim2_models import ServiceProviderConfig
from scim2_models import User
from werkzeug.datastructures import WWWAuthenticate
from werkzeug.exceptions import Unauthorized
from werkzeug.test import Client

from examples.minimal_server import InMemoryStorage
from examples.minimal_server import create_provider
from scim2_flask import SCIM2


def test_validation_error_returns_scim_error(client):
    # A payload that is not even JSON cannot be built with the SCIM client.
    r = client.post("/scim/v2/Users", data=b"{")
    assert r.status_code == 400
    assert r.get_json()["scimType"] == "invalidSyntax"


def test_me_returns_not_implemented(client):
    # RFC7644 §3.11: "A service provider that does NOT support this
    # feature SHOULD respond with HTTP status code 501 (Not
    # Implemented)." The SCIM client has no call for /Me.
    assert client.get("/scim/v2/Me").status_code == 501


@pytest.mark.parametrize("model", [Schema, ResourceType, ServiceProviderConfig])
def test_discovery_endpoints_reject_filter(scim_client, model):
    # RFC7644 §4: "If a "filter" is provided, the service provider SHOULD
    # respond with HTTP status code 403 (Forbidden) to ensure that clients
    # cannot incorrectly assume that any matching conditions specified in
    # a filter are true."
    with pytest.raises(SCIMException) as exc_info:
        scim_client.query(
            model, query_parameters=SearchRequest(filter='userName eq "x"')
        )
    assert exc_info.value.status == 403


def test_patch_is_all_or_nothing(scim_client):
    # RFC7644 §3.5.2: "A PATCH request, regardless of the number of
    # operations, SHALL be treated as atomic. If a single operation
    # encounters an error condition, the original SCIM resource MUST be
    # restored, and a failure status SHALL be returned." The client would
    # refuse to send a PatchOp targeting the read-only "id", so the payload
    # is sent unchecked to reach the server check.
    created = scim_client.create(User[EnterpriseUser](user_name="atomic"))
    patch = {
        "schemas": [str(PatchOp.__schema__)],
        "Operations": [
            {"op": "replace", "path": "displayName", "value": "Should Not Stick"},
            {"op": "replace", "path": "id", "value": "hacked"},
        ],
    }
    with pytest.raises(MutabilityException) as exc_info:
        scim_client.modify(
            User[EnterpriseUser], created.id, patch, check_request_payload=False
        )
    assert exc_info.value.status == 400

    reloaded = scim_client.query(User[EnterpriseUser], created.id)
    assert reloaded.display_name is None


def test_patch_noop_does_not_bump_last_modified(scim_client):
    # RFC7644 §3.5.2.1 (Add Operation): "If the target location already
    # contains the value specified, no changes SHOULD be made to the
    # resource, and a success response SHOULD be returned. Unless other
    # operations change the resource, this operation SHALL NOT change the
    # modify timestamp of the resource."
    created = scim_client.create(
        User[EnterpriseUser](user_name="noop", display_name="Same")
    )
    patch_op = PatchOp[User[EnterpriseUser]](
        operations=[PatchOperation(op="replace", path="displayName", value="Same")]
    )
    scim_client.modify(User[EnterpriseUser], created.id, patch_op)
    reloaded = scim_client.query(User[EnterpriseUser], created.id)
    assert reloaded.meta.last_modified == created.meta.last_modified


def test_replace_unknown_resource_returns_404(scim_client):
    with pytest.raises(SCIMException) as exc_info:
        scim_client.replace(
            User[EnterpriseUser](id="does-not-exist", user_name="ghost")
        )
    assert exc_info.value.status == 404


def test_per_resource_search_endpoint(scim_client):
    created = scim_client.create(User[EnterpriseUser](user_name="searchable"))
    scim_client.create(User[EnterpriseUser](user_name="other"))
    response = scim_client.search(
        SearchRequest[User[EnterpriseUser]](filter='userName eq "searchable"'),
        url="/Users/.search",
    )
    assert [u.id for u in response.resources] == [created.id]


def test_requires_at_least_one_resource_type():
    with pytest.raises(ValueError):
        SCIM2(InMemoryStorage(), ScimProvider())


def test_with_meta_sets_location_when_storage_sets_none(make_scim_client):
    """`_with_meta` computes `meta.location`, which a storage need not keep."""

    class BareStorage(InMemoryStorage):
        def query(self, resource_type, resource_id):
            resource = super().query(resource_type, resource_id)
            resource.meta = Meta(resource_type=resource_type.name)
            return resource

    storage = BareStorage()
    created = storage.create(ResourceType.from_resource(User), User(user_name="bare"))
    app = Flask(__name__)
    SCIM2(storage, ScimProvider(models=[User]), app=app)

    reloaded = make_scim_client(app).query(User, created.id)
    assert reloaded.meta.location == f"http://localhost/scim/v2/Users/{created.id}"


def test_resource_types_are_the_ones_the_provider_declares(make_scim_client):
    resource_type = ResourceType.from_resource(User)
    resource_type.id = resource_type.name = "Account"
    resource_type.endpoint = "/Accounts"
    app = Flask(__name__)
    SCIM2(
        InMemoryStorage(),
        ScimProvider(models=[User], resource_types=[resource_type]),
        app=app,
    )
    client = Client(app)

    response = client.post(
        "/scim/v2/Accounts",
        json={"schemas": [User.__schema__], "userName": "bjensen"},
        content_type="application/scim+json",
    )
    assert response.status_code == 201
    assert response.json["meta"]["resourceType"] == "Account"
    assert response.json["meta"]["location"].startswith(
        "http://localhost/scim/v2/Accounts/"
    )

    response = client.get("/scim/v2/Accounts/unknown")
    assert response.status_code == 404
    assert response.json["detail"] == "Account 'unknown' not found"


@pytest.mark.parametrize(
    ("unknown", "status", "kept"),
    [
        (ScimPolicy.Unknown.forbid, 400, False),
        (ScimPolicy.Unknown.ignore, 201, False),
        (ScimPolicy.Unknown.keep, 201, True),
    ],
)
def test_payloads_are_read_under_the_provider_policy(unknown, status, kept):
    app = Flask(__name__)
    SCIM2(
        InMemoryStorage(),
        ScimProvider(models=[User], policy=ScimPolicy(unknown=unknown)),
        app=app,
    )

    response = Client(app).post(
        "/scim/v2/Users",
        json={"schemas": [User.__schema__], "userName": "bjensen", "bogus": 1},
        content_type="application/scim+json",
    )
    assert response.status_code == status
    assert ("bogus" in response.json) is kept


def test_resource_types_sharing_a_schema_are_served_apart():
    # RFC7643 §6: a resource type binds a schema to an endpoint, so two
    # resource types may share one schema and remain distinct.
    users = ResourceType.from_resource(User)
    admins = ResourceType.from_resource(User)
    admins.id = admins.name = "Admin"
    admins.endpoint = "/Admins"
    app = Flask(__name__)
    SCIM2(
        InMemoryStorage(),
        ScimProvider(models=[User], resource_types=[users, admins]),
        app=app,
    )
    client = Client(app)

    for endpoint, user_name in (("Users", "bjensen"), ("Admins", "root")):
        response = client.post(
            f"/scim/v2/{endpoint}",
            json={"schemas": [User.__schema__], "userName": user_name},
            content_type="application/scim+json",
        )
        assert response.status_code == 201

    listed = client.get("/scim/v2/Admins").json
    assert [r["userName"] for r in listed["Resources"]] == ["root"]

    response = client.post(
        "/scim/v2/.search",
        json={"schemas": ["urn:ietf:params:scim:api:messages:2.0:SearchRequest"]},
        content_type="application/scim+json",
    )
    assert [
        (r["userName"], r["meta"]["resourceType"], r["meta"]["location"].split("/")[-2])
        for r in response.json["Resources"]
    ] == [("bjensen", "User", "Users"), ("root", "Admin", "Admins")]


def test_resource_of_another_type_sharing_the_schema_is_not_found():
    users = ResourceType.from_resource(User)
    admins = ResourceType.from_resource(User)
    admins.id = admins.name = "Admin"
    admins.endpoint = "/Admins"
    app = Flask(__name__)
    SCIM2(
        InMemoryStorage(),
        ScimProvider(models=[User], resource_types=[users, admins]),
        app=app,
    )
    client = Client(app)

    admin = client.post(
        "/scim/v2/Admins",
        json={"schemas": [User.__schema__], "userName": "root"},
        content_type="application/scim+json",
    ).json
    response = client.get(f"/scim/v2/Users/{admin['id']}")
    assert response.status_code == 404
    assert response.json["detail"] == f"User {admin['id']!r} not found"


@pytest.mark.parametrize(
    ("method", "url", "json"),
    [
        ("GET", "/scim/v2/Users", None),
        (
            "POST",
            "/scim/v2/.search",
            {"schemas": ["urn:ietf:params:scim:api:messages:2.0:SearchRequest"]},
        ),
    ],
)
def test_storage_must_name_resource_types(method, url, json):
    class UnnamedStorage(InMemoryStorage):
        def search(self, resource_types, search_request):
            total, resources = super().search(resource_types, search_request)
            for resource in resources:
                resource.meta.resource_type = None
            return total, resources

    app = Flask(__name__)
    app.testing = True
    SCIM2(UnnamedStorage(), ScimProvider(models=[User]), app=app)
    client = Client(app)
    client.post(
        "/scim/v2/Users",
        json={"schemas": [User.__schema__], "userName": "bjensen"},
        content_type="application/scim+json",
    )

    with pytest.raises(ValueError, match="meta.resourceType"):
        client.open(url, method=method, json=json, content_type="application/scim+json")


def test_user_name_is_unique_across_resource_types_sharing_the_user_schema():
    users = ResourceType.from_resource(User)
    admins = ResourceType.from_resource(User)
    admins.id = admins.name = "Admin"
    admins.endpoint = "/Admins"
    app = Flask(__name__)
    SCIM2(
        InMemoryStorage(),
        ScimProvider(models=[User], resource_types=[users, admins]),
        app=app,
    )
    client = Client(app)

    statuses = [
        client.post(
            f"/scim/v2/{endpoint}",
            json={"schemas": [User.__schema__], "userName": "bjensen"},
            content_type="application/scim+json",
        ).status_code
        for endpoint in ("Users", "Admins")
    ]
    assert statuses == [201, 409]


def test_overridden_resource_location_applies_everywhere():
    class CustomSCIM2(SCIM2):
        def resource_location(self, resource_type, resource_id):
            return f"https://scim.example/{resource_type.endpoint.lstrip('/')}/{resource_id}"

    app = Flask(__name__)
    CustomSCIM2(InMemoryStorage(), create_provider(), app=app)
    client = Client(app)

    created = client.post(
        "/scim/v2/Users",
        json={"schemas": [User.__schema__], "userName": "bjensen"},
        content_type="application/scim+json",
    )
    location = f"https://scim.example/Users/{created.json['id']}"
    assert created.json["meta"]["location"] == location
    assert created.headers["Location"] == location

    bulk = client.post(
        "/scim/v2/Bulk",
        json={
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:BulkRequest"],
            "Operations": [
                {"method": "DELETE", "path": f"/Users/{created.json['id']}"},
                {"method": "DELETE", "path": "/Users/unknown"},
            ],
        },
        content_type="application/scim+json",
    )
    assert [op["location"] for op in bulk.json["Operations"]] == [
        location,
        "https://scim.example/Users/unknown",
    ]


def test_http_exception_headers_are_kept():
    """An HTTP error keeps the headers of its exception, such as ``WWW-Authenticate``.

    RFC7644 §2: "a SCIM service provider SHALL indicate supported HTTP
    authentication schemes via the "WWW-Authenticate" header."
    """

    class ProtectedSCIM2(SCIM2):
        def create_blueprint(self):
            blueprint = super().create_blueprint()

            @blueprint.before_request
            def refuse():
                raise Unauthorized(
                    "Missing or invalid token",
                    www_authenticate=WWWAuthenticate("Bearer"),
                )

            return blueprint

    app = Flask(__name__)
    ProtectedSCIM2(InMemoryStorage(), create_provider(), app=app)
    response = Client(app).get("/scim/v2/Users")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.headers["Content-Type"] == "application/scim+json"
    assert response.json["detail"] == "Missing or invalid token"


def test_several_instances_serve_one_application():
    """Instances with their own name serve their own resources, side by side."""
    app = Flask(__name__)
    tenant_a = SCIM2(
        InMemoryStorage(),
        create_provider(),
        app=app,
        url_prefix="/a/scim/v2",
        name="tenant_a",
    )
    tenant_b = SCIM2(
        InMemoryStorage(),
        create_provider(),
        app=app,
        url_prefix="/b/scim/v2",
        name="tenant_b",
    )
    assert app.extensions["scim2"] == {"tenant_a": tenant_a, "tenant_b": tenant_b}
    client = Client(app)

    created = client.post(
        "/a/scim/v2/Users",
        json={"schemas": [User.__schema__], "userName": "bjensen"},
        content_type="application/scim+json",
    )
    assert created.status_code == 201
    assert created.json["meta"]["location"] == (
        f"http://localhost/a/scim/v2/Users/{created.json['id']}"
    )
    assert client.get("/a/scim/v2/Users").json["totalResults"] == 1
    assert client.get("/b/scim/v2/Users").json["totalResults"] == 0

    bulk = client.post(
        "/b/scim/v2/Bulk",
        json={
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:BulkRequest"],
            "Operations": [{"method": "DELETE", "path": "/Unknown/x"}],
        },
        content_type="application/scim+json",
    )
    assert (
        bulk.json["Operations"][0]["location"] == "http://localhost/b/scim/v2/Unknown/x"
    )
