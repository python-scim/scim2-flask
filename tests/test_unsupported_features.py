"""Features the ServiceProviderConfig does not announce are refused or ignored."""

import pytest
from flask import Flask
from scim2_models import Bulk
from scim2_models import BulkOperation
from scim2_models import BulkRequest
from scim2_models import InvalidFilterException
from scim2_models import Patch
from scim2_models import PatchOp
from scim2_models import PatchOperation
from scim2_models import SCIMException
from scim2_models import ScimProvider
from scim2_models import SearchRequest
from scim2_models import ServiceProviderConfig
from scim2_models import User

from examples.minimal_server import InMemoryStorage
from scim2_flask import SCIM2


@pytest.fixture
def scim_client(make_scim_client):
    app = Flask(__name__)
    SCIM2(InMemoryStorage(), ScimProvider(models=[User]), app=app)
    return make_scim_client(app)


def test_listing_without_filter_is_served(scim_client):
    created = scim_client.create(User(user_name="bjensen"))
    response = scim_client.query(User)
    assert [u.id for u in response.resources] == [created.id]


def test_unsupported_filter_is_refused_on_resource_endpoint(scim_client):
    # RFC7644 §3.4.2.2: "When specified, only those resources matching the
    # filter expression SHALL be returned."
    with pytest.raises(InvalidFilterException) as exc_info:
        scim_client.query(
            User, query_parameters=SearchRequest(filter='userName eq "bjensen"')
        )
    assert exc_info.value.status == 400


def test_unsupported_filter_is_refused_on_resource_search(scim_client):
    with pytest.raises(InvalidFilterException):
        scim_client.search(
            SearchRequest[User](filter='userName eq "bjensen"'), url="/Users/.search"
        )


def test_unsupported_filter_is_refused_on_root_search(scim_client):
    with pytest.raises(InvalidFilterException):
        scim_client.search(SearchRequest(filter='userName eq "bjensen"'))


def test_unsupported_bulk_is_refused(scim_client):
    # RFC7644 §3.12, Table 8, "501 (Not Implemented)": "Service provider does
    # not support the request operation, e.g., PATCH."
    bulk_request = BulkRequest[User](
        operations=[
            BulkOperation[User](
                method="POST", bulk_id="u1", path="/Users", data=User(user_name="x")
            )
        ]
    )
    with pytest.raises(SCIMException) as exc_info:
        scim_client.bulk(bulk_request)
    assert exc_info.value.status == 501
    assert exc_info.value.detail == "Bulk operations are not supported"


@pytest.fixture
def unpatchable_scim_client(make_scim_client):
    config = ServiceProviderConfig(
        patch=Patch(supported=False),
        bulk=Bulk(supported=True, max_operations=10, max_payload_size=1_048_576),
    )
    app = Flask(__name__)
    SCIM2(InMemoryStorage(), ScimProvider(models=[User], config=config), app=app)
    return make_scim_client(app)


def test_unsupported_patch_is_refused(unpatchable_scim_client):
    # RFC7644 §3.12, Table 8, "501 (Not Implemented)": "Service provider does
    # not support the request operation, e.g., PATCH."
    created = unpatchable_scim_client.create(User(user_name="bjensen"))
    patch_op = PatchOp[User](
        operations=[PatchOperation(op="replace", path="displayName", value="Babs")]
    )
    with pytest.raises(SCIMException) as exc_info:
        unpatchable_scim_client.modify(User, created.id, patch_op)
    assert exc_info.value.status == 501
    assert exc_info.value.detail == "PATCH is not supported"
    assert unpatchable_scim_client.query(User, created.id).display_name is None


def test_unsupported_patch_is_refused_in_bulk(unpatchable_scim_client):
    created = unpatchable_scim_client.create(User(user_name="bjensen"))
    bulk_request = BulkRequest[User](
        operations=[
            BulkOperation[User](
                method="PATCH",
                path=f"/Users/{created.id}",
                data=PatchOp[User](
                    operations=[
                        PatchOperation(op="replace", path="displayName", value="Babs")
                    ]
                ),
            )
        ]
    )
    response = unpatchable_scim_client.bulk(bulk_request)
    operation = response.operations[0]
    assert operation.status == 501
    assert operation.response.detail == "PATCH is not supported"
    assert operation.location.endswith(f"/Users/{created.id}")
    assert unpatchable_scim_client.query(User, created.id).display_name is None
