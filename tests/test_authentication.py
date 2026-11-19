import pytest

from examples.authentication import create_app


@pytest.fixture
def protected_client():
    return create_app().test_client()


def test_example_authentication_accepts_a_known_bearer_token(protected_client):
    response = protected_client.get(
        "/scim/v2/Users", headers={"Authorization": "Bearer secret"}
    )

    assert response.status_code == 200


def test_example_authentication_refuses_a_token_without_scheme(protected_client):
    response = protected_client.get(
        "/scim/v2/Users", headers={"Authorization": "secret"}
    )

    assert response.status_code == 401


def test_example_authentication_refuses_a_token_of_another_scheme(protected_client):
    response = protected_client.get(
        "/scim/v2/Users", headers={"Authorization": "Basic secret"}
    )

    assert response.status_code == 401


def test_example_authentication_accepts_the_scheme_in_any_case(protected_client):
    """Per RFC 9110 §11.1, the authentication scheme is case-insensitive."""
    response = protected_client.get(
        "/scim/v2/Users", headers={"Authorization": "bearer secret"}
    )

    assert response.status_code == 200
