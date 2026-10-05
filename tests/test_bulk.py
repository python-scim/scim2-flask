"""Tests for the POST /Bulk endpoint, RFC7644 §3.7."""

import pytest
from scim2_models import BulkOperation
from scim2_models import BulkRequest
from scim2_models import Context
from scim2_models import EnterpriseUser
from scim2_models import PatchOp
from scim2_models import PatchOperation
from scim2_models import SCIMException
from scim2_models import User


def test_bulk_dispatches_operations_by_method(scim_client):
    # RFC7644 §3.7: "The body of a bulk operation contains a set of HTTP
    # resource operations using one of the HTTP methods supported by the
    # API, i.e., POST, PUT, PATCH, or DELETE."
    create = scim_client.bulk(
        BulkRequest[User[EnterpriseUser]](
            operations=[
                BulkOperation[User[EnterpriseUser]](
                    method="POST",
                    bulk_id="u1",
                    path="/Users",
                    data=User[EnterpriseUser](user_name="bulk-created"),
                )
            ]
        )
    )
    assert create.operations[0].status == 201
    uid = create.operations[0].location.rsplit("/", 1)[-1]

    modify = scim_client.bulk(
        BulkRequest[User[EnterpriseUser]](
            operations=[
                BulkOperation[User[EnterpriseUser]](
                    method="PATCH",
                    bulk_id="p1",
                    path=f"/Users/{uid}",
                    data=PatchOp[User[EnterpriseUser]](
                        operations=[
                            PatchOperation(
                                op="replace", path="displayName", value="Bulked"
                            )
                        ]
                    ),
                ),
                BulkOperation[User[EnterpriseUser]](
                    method="PUT",
                    bulk_id="r1",
                    path=f"/Users/{uid}",
                    data=User[EnterpriseUser](
                        user_name="bulk-created", display_name="Replaced"
                    ),
                ),
                BulkOperation[User[EnterpriseUser]](
                    method="DELETE", bulk_id="d1", path=f"/Users/{uid}"
                ),
            ]
        )
    )
    assert [op.status for op in modify.operations] == [200, 200, 204]

    with pytest.raises(SCIMException) as exc_info:
        scim_client.query(User[EnterpriseUser], uid)
    assert exc_info.value.status == 404


def test_bulk_rejects_job_exceeding_max_operations(client):
    # RFC7644 §3.7.4: "If either limit is exceeded, the service provider
    # MUST return HTTP response code 413 (Payload Too Large)."
    bulk_request = BulkRequest[User[EnterpriseUser]](
        operations=[
            BulkOperation[User[EnterpriseUser]](
                method="POST",
                bulk_id=f"u{i}",
                path="/Users",
                data=User[EnterpriseUser](user_name=f"bulk{i}"),
            )
            for i in range(101)
        ]
    )
    # scim2-client refuses to send a job beyond the limits the provider
    # announces, so the server side is exercised through a raw request.
    response = client.post(
        "/scim/v2/Bulk",
        data=bulk_request.model_dump_json(scim_ctx=Context.BULK_REQUEST),
        content_type="application/scim+json",
    )
    assert response.status_code == 413
    assert "maxOperations" in response.json["detail"]


def test_bulk_stops_after_fail_on_errors(scim_client):
    # RFC7644 §3.7: "The "failOnErrors" attribute defines the number of
    # errors that the service provider should accept before failing the
    # remaining operations returning the response."
    response = scim_client.bulk(
        BulkRequest[User[EnterpriseUser]](
            fail_on_errors=1,
            operations=[
                BulkOperation[User[EnterpriseUser]](
                    method="DELETE", bulk_id="bad", path="/Users/does-not-exist"
                ),
                BulkOperation[User[EnterpriseUser]](
                    method="POST",
                    bulk_id="never",
                    path="/Users",
                    data=User[EnterpriseUser](user_name="unreached"),
                ),
            ],
        )
    )
    assert [op.status for op in response.operations] == [404]


def test_bulk_operation_errors_are_embedded_per_operation(scim_client):
    # RFC7644 §3.7: "The service provider MUST continue performing as many
    # changes as possible and disregard partial failures."
    scim_client.create(User[EnterpriseUser](user_name="taken"))

    response = scim_client.bulk(
        BulkRequest[User[EnterpriseUser]](
            operations=[
                BulkOperation[User[EnterpriseUser]](
                    method="DELETE", bulk_id="unknown-path", path="/Bogus/xyz"
                ),
                BulkOperation[User[EnterpriseUser]](
                    method="POST",
                    bulk_id="dupe",
                    path="/Users",
                    data=User[EnterpriseUser](user_name="taken"),
                ),
            ]
        )
    )
    unknown, dupe = response.operations
    assert unknown.status == 404
    # RFC7644 §3.7.3: "A "location" attribute that includes the resource's
    # endpoint MUST be returned for all operations except for failed POST
    # operations (which have no location)." That holds even when the path
    # designates no resource type.
    assert unknown.location == "http://localhost/scim/v2/Bogus/xyz"
    assert dupe.status == 409
    assert dupe.response.scim_type == "uniqueness"


@pytest.mark.parametrize(
    ("method", "data"),
    [
        ("PUT", User[EnterpriseUser](user_name="whoever")),
        (
            "PATCH",
            PatchOp[User[EnterpriseUser]](
                operations=[
                    PatchOperation(op="replace", path="displayName", value="Nobody")
                ]
            ),
        ),
        ("DELETE", None),
    ],
    ids=["PUT", "PATCH", "DELETE"],
)
def test_bulk_operation_without_resource_id_is_not_found(scim_client, method, data):
    # RFC7644 §3.12, Table 8, "404 (Not Found)": "Specified resource (e.g.,
    # User) or endpoint does not exist." A PUT, PATCH or DELETE on the
    # endpoint itself designates no resource, as outside a bulk.
    response = scim_client.bulk(
        BulkRequest[User[EnterpriseUser]](
            operations=[
                BulkOperation[User[EnterpriseUser]](
                    method=method, bulk_id="no-id", path="/Users", data=data
                ),
                BulkOperation[User[EnterpriseUser]](
                    method="POST",
                    bulk_id="next",
                    path="/Users",
                    data=User[EnterpriseUser](user_name="still-created"),
                ),
            ]
        )
    )
    no_id, created = response.operations
    assert no_id.status == 404
    assert no_id.location == "http://localhost/scim/v2/Users"
    assert created.status == 201


def test_bulk_post_on_a_resource_is_not_found(scim_client):
    # As outside a bulk, a POST creates a resource on an endpoint, not at a
    # given resource location.
    response = scim_client.bulk(
        BulkRequest[User[EnterpriseUser]](
            operations=[
                BulkOperation[User[EnterpriseUser]](
                    method="POST",
                    bulk_id="with-id",
                    path="/Users/chosen-id",
                    data=User[EnterpriseUser](user_name="not-created"),
                )
            ]
        )
    )
    assert response.operations[0].status == 404
    # RFC7644 §3.7.3: failed POST operations "have no location".
    assert response.operations[0].location is None
    assert scim_client.query(User[EnterpriseUser]).total_results == 0


def test_bulk_rejects_job_exceeding_max_payload_size(client):
    # RFC7644 §3.7.4: "The service provider MUST define the maximum
    # number of operations and maximum payload size a client may send in
    # a single request. [...] If either limit is exceeded, the service
    # provider MUST return HTTP response code 413 (Payload Too Large)."
    bulk_request = BulkRequest[User[EnterpriseUser]](
        operations=[
            BulkOperation[User[EnterpriseUser]](
                method="POST",
                bulk_id="u1",
                path="/Users",
                data=User[EnterpriseUser](user_name="x" * 2_000_000),
            )
        ]
    )
    # scim2-client refuses to send a job beyond the limits the provider
    # announces, so the server side is exercised through a raw request.
    response = client.post(
        "/scim/v2/Bulk",
        data=bulk_request.model_dump_json(scim_ctx=Context.BULK_REQUEST),
        content_type="application/scim+json",
    )
    assert response.status_code == 413
    assert response.headers["Content-Type"] == "application/scim+json"
    assert response.json["status"] == "413"


def test_bulk_stale_operation_version_returns_412(scim_client):
    # RFC7644 §3.7: "Version MAY be used if the service provider supports
    # entity-tags (ETags) (Section 2.3 of [RFC7232]) and "method" is "PUT",
    # "PATCH", or "DELETE"."
    created = scim_client.create(User[EnterpriseUser](user_name="bulk-versioned"))

    response = scim_client.bulk(
        BulkRequest[User[EnterpriseUser]](
            operations=[
                BulkOperation[User[EnterpriseUser]](
                    method="PUT",
                    bulk_id="v1",
                    path=f"/Users/{created.id}",
                    version='W/"stale"',
                    data=User[EnterpriseUser](
                        user_name="bulk-versioned", display_name="Should Not Stick"
                    ),
                )
            ]
        )
    )
    assert response.operations[0].status == 412
    # RFC7644 §3.7.3: "A "location" attribute that includes the resource's
    # endpoint MUST be returned for all operations except for failed POST
    # operations (which have no location)." So it must be present even on
    # this 412.
    assert response.operations[0].location.endswith(f"/Users/{created.id}")
    # The version of a result is the one of the resource, never the one the
    # client expected.
    assert response.operations[0].version is None

    reloaded = scim_client.query(User[EnterpriseUser], created.id)
    assert reloaded.display_name is None


def test_bulk_delete_with_stale_version_returns_412(scim_client):
    created = scim_client.create(User[EnterpriseUser](user_name="bulk-kept"))

    response = scim_client.bulk(
        BulkRequest[User[EnterpriseUser]](
            operations=[
                BulkOperation[User[EnterpriseUser]](
                    method="DELETE",
                    path=f"/Users/{created.id}",
                    version='W/"stale"',
                )
            ]
        )
    )
    assert response.operations[0].status == 412
    assert scim_client.query(User[EnterpriseUser], created.id).id == created.id


def test_bulk_delete_result_carries_no_version(scim_client):
    created = scim_client.create(User[EnterpriseUser](user_name="bulk-deleted"))

    response = scim_client.bulk(
        BulkRequest[User[EnterpriseUser]](
            operations=[
                BulkOperation[User[EnterpriseUser]](
                    method="DELETE",
                    path=f"/Users/{created.id}",
                    version=created.meta.version,
                )
            ]
        )
    )
    assert response.operations[0].status == 204
    assert response.operations[0].version is None


def test_bulk_keeps_stricter_application_limit(app, client):
    app.config["MAX_CONTENT_LENGTH"] = 10
    response = client.post(
        "/scim/v2/Bulk",
        json={
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:BulkRequest"],
            "Operations": [{"method": "DELETE", "path": "/Users/unknown"}],
        },
        content_type="application/scim+json",
    )
    assert response.status_code == 413
