"""Minimal SCIM server built with scim2-flask.

Run it with:

    uv run python examples/minimal_server.py
"""

from flask import Flask
from scim2_models import Bulk
from scim2_models import ChangePassword
from scim2_models import EnterpriseUser
from scim2_models import ETag
from scim2_models import Filter
from scim2_models import Group
from scim2_models import Patch
from scim2_models import ResourceType
from scim2_models import ScimProvider
from scim2_models import ServiceProviderConfig
from scim2_models import Sort
from scim2_models import User
from scim2_server.memory import InMemoryStorage

from scim2_flask import ScimServer

MAX_RESULTS = 50
MAX_BULK_OPERATIONS = 100
MAX_BULK_PAYLOAD_SIZE = 1_048_576


def create_provider() -> ScimProvider:
    return ScimProvider(
        models=[User, EnterpriseUser, Group],
        resource_types=[
            ResourceType.from_resource(User[EnterpriseUser]),
            ResourceType.from_resource(Group),
        ],
        config=ServiceProviderConfig(
            patch=Patch(supported=True),
            bulk=Bulk(
                supported=True,
                max_operations=MAX_BULK_OPERATIONS,
                max_payload_size=MAX_BULK_PAYLOAD_SIZE,
            ),
            filter=Filter(supported=True, max_results=MAX_RESULTS),
            change_password=ChangePassword(supported=False),
            sort=Sort(supported=True),
            etag=ETag(supported=True),
            authentication_schemes=[],
        ),
    )


def create_app() -> Flask:
    app = Flask(__name__)
    scim_server = ScimServer(InMemoryStorage(), create_provider())
    scim_server.init_app(app)
    return app


if __name__ == "__main__":
    create_app().run(debug=True)
