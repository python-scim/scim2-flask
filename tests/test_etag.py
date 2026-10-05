"""Tests for resource versioning (ETags), RFC7644 §3.14."""

import pytest
from flask import Flask
from scim2_models import EnterpriseUser
from scim2_models import ETag
from scim2_models import PatchOp
from scim2_models import PatchOperation
from scim2_models import SCIMException
from scim2_models import ScimProvider
from scim2_models import ServiceProviderConfig
from scim2_models import User

from examples.minimal_server import InMemoryStorage
from scim2_flask import SCIM2


def test_etag_header_mirrors_meta_version(client):
    # RFC7644 §3.14: "When supported, SCIM ETags MUST be specified as an
    # HTTP header and SHOULD be specified within the 'version' attribute
    # contained in the resource's 'meta' attribute." The SCIM client only
    # exposes the payload, so the header is read from the raw response.
    r = client.post(
        "/scim/v2/Users",
        json={"schemas": [User.__schema__], "userName": "etagged"},
    )
    assert r.headers["ETag"] == r.get_json()["meta"]["version"]


def test_conditional_get_returns_304(scim_client):
    # RFC7644 §3.14: "If the resource has not changed, the service
    # provider simply returns an empty body with a 304 (Not Modified)
    # response code."
    created = scim_client.create(User[EnterpriseUser](user_name="etagged"))
    etag = created.meta.version

    not_modified = scim_client.query(
        User[EnterpriseUser], created.id, headers={"If-None-Match": etag}
    )
    assert not_modified is None

    reloaded = scim_client.query(
        User[EnterpriseUser], created.id, headers={"If-None-Match": 'W/"stale"'}
    )
    assert reloaded.id == created.id


def test_stale_if_match_returns_412(scim_client):
    # RFC7644 §3.14: "If the service provider supports versioning of
    # resources, the client MAY supply an If-Match header (Section 3.1 of
    # [RFC7232]) for PUT and PATCH operations to ensure that the requested
    # operation succeeds only if the supplied ETag matches the latest
    # service provider resource [...]."
    # RFC7644 §3.12, Table 8, "412 (Precondition Failed)": "Failed to
    # update. Resource has changed on the server."
    created = scim_client.create(User[EnterpriseUser](user_name="stale"))
    stale_etag = created.meta.version

    def replace_display_name(value):
        return PatchOp[User[EnterpriseUser]](
            operations=[PatchOperation(op="replace", path="displayName", value=value)]
        )

    scim_client.modify(
        User[EnterpriseUser],
        created.id,
        replace_display_name("First"),
        headers={"If-Match": stale_etag},
    )

    with pytest.raises(SCIMException) as exc_info:
        scim_client.modify(
            User[EnterpriseUser],
            created.id,
            replace_display_name("Second"),
            headers={"If-Match": stale_etag},
        )
    assert exc_info.value.status == 412

    reloaded = scim_client.query(User[EnterpriseUser], created.id)
    assert reloaded.display_name == "First"


def test_if_match_wildcard_bypasses_version_check(scim_client):
    created = scim_client.create(User[EnterpriseUser](user_name="wildcard"))
    scim_client.delete(User[EnterpriseUser], created.id, headers={"If-Match": "*"})

    with pytest.raises(SCIMException) as exc_info:
        scim_client.query(User[EnterpriseUser], created.id)
    assert exc_info.value.status == 404


def test_if_match_is_a_noop_without_meta_version(make_scim_client):
    """`If-Match` must be ignored, not rejected, on a resource without version.

    Versioning is announced, but the storage does not set `meta.version`.
    """

    class UnversionedStorage(InMemoryStorage):
        def create(self, resource_type, resource):
            resource = super().create(resource_type, resource)
            resource.meta.version = None
            return resource

    app = Flask(__name__)
    config = ServiceProviderConfig(etag=ETag(supported=True))
    SCIM2(UnversionedStorage(), ScimProvider(models=[User], config=config), app=app)
    scim_client = make_scim_client(app)

    created = scim_client.create(User(user_name="unversioned"))
    assert created.meta.version is None

    scim_client.delete(User, created.id, headers={"If-Match": 'W/"anything"'})
    with pytest.raises(SCIMException) as exc_info:
        scim_client.query(User, created.id)
    assert exc_info.value.status == 404
