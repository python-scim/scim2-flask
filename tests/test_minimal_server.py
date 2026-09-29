import pytest
from scim2_models import EnterpriseUser
from scim2_models import ResourceType
from scim2_models import SearchRequest
from scim2_models import UniquenessException
from scim2_models import User

from examples.minimal_server import InMemoryStorage
from scim2_flask import ResourceNotFoundError


def test_uniqueness_conflict_on_user_name(scim_client):
    scim_client.create(User[EnterpriseUser](user_name="dupe"))
    with pytest.raises(UniquenessException) as exc_info:
        scim_client.create(User[EnterpriseUser](user_name="dupe"))
    assert exc_info.value.status == 409


def test_search_filters_and_sorts(scim_client):
    scim_client.create(
        User[EnterpriseUser](user_name="charlie", emails=[User.Emails(value="c@x.com")])
    )
    scim_client.create(
        User[EnterpriseUser](
            user_name="alice", emails=[User.Emails(value="a@x.com", primary=True)]
        )
    )
    response = scim_client.query(
        User[EnterpriseUser],
        query_parameters=SearchRequest(filter="userName pr", sort_by="emails"),
    )
    values = [u.emails[0].value for u in response.resources]
    assert values == sorted(values)


def test_sort_puts_resources_without_a_value_last(scim_client):
    scim_client.create(
        User[EnterpriseUser](
            user_name="has-email", emails=[User.Emails(value="a@x.com")]
        )
    )
    scim_client.create(User[EnterpriseUser](user_name="no-email"))
    response = scim_client.query(
        User[EnterpriseUser], query_parameters=SearchRequest(sort_by="emails")
    )
    assert [u.user_name for u in response.resources] == ["has-email", "no-email"]


def test_update_unknown_resource_raises():
    storage = InMemoryStorage()
    with pytest.raises(ResourceNotFoundError):
        storage.update(
            ResourceType.from_resource(User[EnterpriseUser]),
            User[EnterpriseUser](id="does-not-exist", user_name="ghost"),
        )


def test_tutorial_smoke(client):
    """Send the requests of the tutorial, and check the answers it shows."""
    headers = {"Content-Type": "application/scim+json"}
    user_payload = {
        "schemas": [
            "urn:ietf:params:scim:schemas:core:2.0:User",
            "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User",
        ],
        "userName": "bjensen",
        "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User": {
            "employeeNumber": "42"
        },
    }

    response = client.post("/scim/v2/Users", json=user_payload, headers=headers)
    assert response.status_code == 201
    user = response.json
    assert user["userName"] == "bjensen"
    assert user["urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"] == {
        "employeeNumber": "42"
    }
    assert user["meta"]["resourceType"] == "User"
    assert user["meta"]["location"].endswith(f"/scim/v2/Users/{user['id']}")

    response = client.get(user["meta"]["location"])
    assert response.status_code == 200
    assert response.json == user

    response = client.post("/scim/v2/Users", json=user_payload, headers=headers)
    assert response.status_code == 409
    assert response.json["scimType"] == "uniqueness"
    assert response.json["detail"] == "userName 'bjensen' is already taken"

    response = client.post(
        "/scim/v2/Groups",
        json={
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"],
            "displayName": "Engineers",
        },
        headers=headers,
    )
    assert response.status_code == 201
    group = response.json
    assert group["displayName"] == "Engineers"
    assert group["meta"]["resourceType"] == "Group"

    response = client.get("/scim/v2/Groups")
    assert response.status_code == 200
    assert response.json["totalResults"] == 1
    assert response.json["Resources"] == [group]
