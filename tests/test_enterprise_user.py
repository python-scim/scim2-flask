import pytest
from scim2_models import EnterpriseUser
from scim2_models import PatchOp
from scim2_models import PatchOperation
from scim2_models import ResourceType
from scim2_models import Schema
from scim2_models import SchemaExtension
from scim2_models import SearchRequest
from scim2_models import User


@pytest.fixture
def user(scim_client):
    return scim_client.create(
        User[EnterpriseUser](
            user_name="bjensen",
            EnterpriseUser=EnterpriseUser(employee_number="42"),
        )
    )


def test_extension_attributes_are_stored_and_returned(scim_client, user):
    reloaded = scim_client.query(User[EnterpriseUser], user.id)
    assert reloaded.schemas == [User.__schema__, EnterpriseUser.__schema__]
    assert reloaded[EnterpriseUser].employee_number == "42"


def test_meta_resource_type_is_the_resource_type_name(user):
    # RFC7643 §3.1: "resourceType The name of the resource type of the
    # resource." The name of the model carrying the extension is not that
    # name.
    assert user.meta.resource_type == "User"


def test_not_found_detail_names_the_resource_type(client):
    response = client.get("/scim/v2/Users/unknown")
    assert response.status_code == 404
    assert response.json["detail"] == "User 'unknown' not found"


def test_filter_on_extension_attribute(scim_client, user):
    response = scim_client.query(
        User[EnterpriseUser],
        query_parameters=SearchRequest(
            filter=f'{EnterpriseUser.__schema__}:employeeNumber eq "42"'
        ),
    )
    assert [u.id for u in response.resources] == [user.id]


def test_patch_extension_attribute(scim_client, user):
    patch_op = PatchOp[User[EnterpriseUser]](
        operations=[
            PatchOperation(
                op="replace",
                path=f"{EnterpriseUser.__schema__}:department",
                value="R&D",
            )
        ]
    )
    patched = scim_client.modify(User[EnterpriseUser], user.id, patch_op)
    assert patched[EnterpriseUser].employee_number == "42"
    assert patched[EnterpriseUser].department == "R&D"


def test_discovery_announces_the_extension(scim_client):
    # RFC7643 §6: "schemaExtensions A list of URIs of the resource type's
    # schema extensions."
    resource_type = scim_client.query(ResourceType, "User")
    assert resource_type.schema_ == User.__schema__
    assert resource_type.schema_extensions == [
        SchemaExtension(schema_=EnterpriseUser.__schema__, required=False)
    ]

    schemas = scim_client.query(Schema)
    assert EnterpriseUser.__schema__ in [schema.id for schema in schemas.resources]
