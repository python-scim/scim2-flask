from abc import ABC
from abc import abstractmethod
from http import HTTPStatus
from typing import Any

from scim2_models import Resource
from scim2_models import ResourceType
from scim2_models import SCIMException
from scim2_models import SearchRequest


class ResourceNotFoundError(SCIMException):
    """Raised by a :class:`ScimStorage` when no resource matches an id.

    :rfc:`RFC7644 §3.12 <7644#section-3.12>`, Table 8, "404 (Not Found)":
    "Specified resource (e.g., User) or endpoint does not exist."
    """

    status = HTTPStatus.NOT_FOUND

    def __init__(self, resource_type: ResourceType, resource_id: str):
        self.resource_type = resource_type
        self.resource_id = resource_id
        super().__init__(detail=f"{resource_type.name} {resource_id!r} not found")


class ScimStorage(ABC):
    """Where :class:`~scim2_flask.SCIM2` reads and writes SCIM resources.

    Subclass it to connect the SCIM server to your own data (SQL, LDAP,
    in-memory, ...). The server handles the SCIM protocol and calls these
    methods to query, search, create, update and delete resources.

    Every method receives the :class:`~scim2_models.ResourceType` it applies
    to, so a single storage can serve several resource types.
    """

    @abstractmethod
    def query(self, resource_type: ResourceType, resource_id: str) -> Resource[Any]:
        """Return the resource of ``resource_type`` identified by ``resource_id``.

        :raises ResourceNotFoundError: if no such resource exists.
        """

    @abstractmethod
    def search(
        self,
        resource_types: list[ResourceType],
        search_request: SearchRequest,
    ) -> tuple[int, list[Resource[Any]]]:
        """Return the total count and one page of the matching resources.

        ``resource_types`` holds a single resource type for a search on its
        endpoint (such as ``/Users`` or ``/Groups``), and all of them for a
        search at the server root (``/.search``): filter, sort and page them
        as a single collection. An attribute a resource type does not declare
        matches none of its resources.

        :param resource_types: The resource types to search.
        :param search_request: The query: ``filter``, ``sort_by``,
            ``sort_order``, ``start_index_0`` and ``stop_index_0``.
        :return: ``(total_results, page)``, the page holding at most
            ``maxResults`` resources.
        :raises ~scim2_models.TooManyException: if the query yields more
            results than the storage is willing to process.
        """

    @abstractmethod
    def create(
        self, resource_type: ResourceType, resource: Resource[Any]
    ) -> Resource[Any]:
        """Persist ``resource`` and return the stored representation."""

    @abstractmethod
    def update(
        self, resource_type: ResourceType, resource: Resource[Any]
    ) -> Resource[Any]:
        """Persist ``resource``, identified by its own ``id``, and return the stored representation.

        Used for both PUT replacements and PATCH modifications: in both
        cases the caller has already produced the resource's full wanted
        state and only asks for it to be saved.

        :raises ResourceNotFoundError: if no resource matches ``resource.id``.
        """

    @abstractmethod
    def delete(self, resource_type: ResourceType, resource_id: str) -> None:
        """Remove the resource of ``resource_type`` identified by ``resource_id``.

        :raises ResourceNotFoundError: if no such resource exists.
        """
