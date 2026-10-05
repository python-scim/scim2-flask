"""Tests for the POST /.search endpoint at the server root, RFC7644 §3.4.3."""

import pytest
from scim2_models import Group
from scim2_models import User


@pytest.fixture
def root_search(client):
    """Populate users A, B, C and groups B2, Z, and return a root search helper."""
    for name in ("a", "b", "c"):
        client.post(
            "/scim/v2/Users",
            json={
                "schemas": [User.__schema__],
                "userName": name,
                "displayName": name.upper(),
            },
            content_type="application/scim+json",
        )
    for name in ("B2", "Z"):
        client.post(
            "/scim/v2/Groups",
            json={"schemas": [Group.__schema__], "displayName": name},
            content_type="application/scim+json",
        )

    def search(**parameters):
        response = client.post(
            "/scim/v2/.search",
            json={
                "schemas": ["urn:ietf:params:scim:api:messages:2.0:SearchRequest"],
                **parameters,
            },
            content_type="application/scim+json",
        )
        assert response.status_code == 200
        return response.json

    return search


def display_names(response):
    return [resource["displayName"] for resource in response["Resources"]]


def test_root_search_gathers_every_resource_type(root_search):
    # RFC7644 §3.4.3: "Clients MAY execute queries without passing parameters
    # on the URL by using the HTTP POST verb combined with the "/.search"
    # path extension."
    response = root_search()
    assert response["totalResults"] == 5
    assert [r["meta"]["resourceType"] for r in response["Resources"]] == [
        "User",
        "User",
        "User",
        "Group",
        "Group",
    ]


def test_root_search_pages_across_resource_types(root_search):
    # RFC7644 §3.4.2.4: "count Non-negative integer. Specifies the desired
    # maximum number of query results per page"
    response = root_search(startIndex=3, count=2)
    assert response["totalResults"] == 5
    assert response["startIndex"] == 3
    assert response["itemsPerPage"] == 2
    assert display_names(response) == ["C", "B2"]


def test_root_search_sorts_across_resource_types(root_search):
    response = root_search(sortBy="displayName", sortOrder="descending")
    assert display_names(response) == ["Z", "C", "B2", "B", "A"]


def test_root_search_filter_on_an_attribute_of_one_resource_type(root_search):
    # RFC7644 §3.4.2.1: "for filtered attributes that are not part of a
    # particular resource type, the service provider SHALL treat the
    # attribute as if there is no attribute value."
    response = root_search(filter='userName eq "a"')
    assert display_names(response) == ["A"]
