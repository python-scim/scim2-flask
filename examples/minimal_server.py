"""Minimal SCIM server built with scim2-flask.

Run it with:

    uv run python examples/minimal_server.py
"""

import hashlib
import json
from collections import defaultdict
from datetime import UTC
from datetime import datetime
from typing import Any
from uuid import uuid4

from flask import Flask
from scim2_models import Bulk
from scim2_models import ChangePassword
from scim2_models import EnterpriseUser
from scim2_models import ETag
from scim2_models import Filter
from scim2_models import Group
from scim2_models import Meta
from scim2_models import Patch
from scim2_models import Resource
from scim2_models import ResourceType
from scim2_models import ScimProvider
from scim2_models import SearchRequest
from scim2_models import ServiceProviderConfig
from scim2_models import Sort
from scim2_models import UniquenessException
from scim2_models import User

from scim2_flask import SCIM2
from scim2_flask import ResourceNotFoundError
from scim2_flask import ScimStorage

MAX_RESULTS = 50
MAX_BULK_OPERATIONS = 100
MAX_BULK_PAYLOAD_SIZE = 1_048_576


def make_etag(resource: Resource[Any]) -> str:
    """Compute a weak ETag from a resource's content."""
    content = resource.model_dump(
        mode="json", exclude={"meta": {"version", "location"}}, scim_ctx=None
    )
    digest = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()
    return f'W/"{digest[:16]}"'


class InMemoryStorage(ScimStorage):
    """Keeps resources in memory; a real deployment would use SQL, LDAP, or another backend."""

    def __init__(self) -> None:
        self.resources: dict[str, dict[str, Resource[Any]]] = defaultdict(dict)

    def query(self, resource_type: ResourceType, resource_id: str) -> Resource[Any]:
        try:
            return self.resources[resource_type.name][resource_id]
        except KeyError:
            raise ResourceNotFoundError(resource_type, resource_id) from None

    def search(
        self,
        resource_types: list[ResourceType],
        search_request: SearchRequest,
    ) -> tuple[int, list[Resource[Any]]]:
        resources = [
            resource
            for resource_type in resource_types
            for resource in self.resources[resource_type.name].values()
        ]
        if search_request.filter:
            resources = [r for r in resources if search_request.filter.match(r)]
        resources = search_request.sort(resources)
        start = search_request.start_index_0 or 0
        count = (
            search_request.count if search_request.count is not None else MAX_RESULTS
        )
        stop = start + min(count, MAX_RESULTS)
        return len(resources), resources[start:stop]

    def create(
        self, resource_type: ResourceType, resource: Resource[Any]
    ) -> Resource[Any]:
        self._check_user_name_unique(resource)
        now = datetime.now(UTC)
        resource.id = str(uuid4())
        resource.meta = Meta(
            resource_type=resource_type.name, created=now, last_modified=now
        )
        resource.meta.version = make_etag(resource)
        self.resources[resource_type.name][resource.id] = resource
        return resource

    def update(
        self, resource_type: ResourceType, resource: Resource[Any]
    ) -> Resource[Any]:
        store = self.resources[resource_type.name]
        if resource.id not in store:
            raise ResourceNotFoundError(resource_type, resource.id)
        self._check_user_name_unique(resource)
        created = store[resource.id].meta.created if store[resource.id].meta else None
        resource.meta = Meta(
            resource_type=resource_type.name,
            created=created,
            last_modified=datetime.now(UTC),
        )
        resource.meta.version = make_etag(resource)
        store[resource.id] = resource
        return resource

    def _check_user_name_unique(self, resource: Resource[Any]) -> None:
        user_name = getattr(resource, "user_name", None)
        if user_name is None:
            return
        for existing in (
            r for store in self.resources.values() for r in store.values()
        ):
            if (
                existing.id != resource.id
                and getattr(existing, "user_name", None) == user_name
            ):
                raise UniquenessException(
                    attribute="userName",
                    value=user_name,
                    detail=f"userName {user_name!r} is already taken",
                )

    def delete(self, resource_type: ResourceType, resource_id: str) -> None:
        try:
            del self.resources[resource_type.name][resource_id]
        except KeyError:
            raise ResourceNotFoundError(resource_type, resource_id) from None


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
    scim2 = SCIM2(InMemoryStorage(), create_provider())
    scim2.init_app(app)
    return app


if __name__ == "__main__":
    create_app().run(debug=True)
