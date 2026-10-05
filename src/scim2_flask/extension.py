from __future__ import annotations

from functools import reduce
from http import HTTPStatus
from operator import or_
from typing import Any
from typing import TypeVar
from typing import cast

from flask import Blueprint
from flask import Flask
from flask import Response
from flask import current_app
from flask import g
from flask import jsonify
from flask import request
from flask import url_for
from pydantic import ValidationError
from scim2_models import Bulk
from scim2_models import BulkOperation
from scim2_models import BulkRequest
from scim2_models import BulkResponse
from scim2_models import ChangePassword
from scim2_models import Context
from scim2_models import Error
from scim2_models import ETag
from scim2_models import Filter
from scim2_models import InvalidFilterException
from scim2_models import ListResponse
from scim2_models import Meta
from scim2_models import Patch
from scim2_models import PatchOp
from scim2_models import Resource
from scim2_models import ResourceType
from scim2_models import ResponseParameters
from scim2_models import Schema
from scim2_models import SCIMException
from scim2_models import ScimProvider
from scim2_models import SearchRequest
from scim2_models import ServiceProviderConfig
from scim2_models import Sort
from werkzeug.datastructures import ETags
from werkzeug.exceptions import Forbidden
from werkzeug.exceptions import HTTPException
from werkzeug.exceptions import MethodNotAllowed
from werkzeug.exceptions import NotFound
from werkzeug.exceptions import NotImplemented as HTTPNotImplemented
from werkzeug.http import parse_etags
from werkzeug.routing import MapAdapter
from werkzeug.wrappers import Response as WerkzeugResponse

from .storage import ScimStorage

EXTENSION_NAME = "scim2"

GenericT = TypeVar("GenericT")


def _parametrize(generic: type[GenericT], parameter: Any) -> type[GenericT]:
    """Parametrize a generic class with a type only known at runtime."""
    return cast(type[GenericT], cast(Any, generic)[parameter])


class PayloadTooLargeException(SCIMException):
    """A bulk job beyond the limits the service provider announces.

    :rfc:`RFC7644 §3.7.4 <7644#section-3.7.4>`: "If either limit is
    exceeded, the service provider MUST return HTTP response code 413
    (Payload Too Large)." No scimType of Table 9 goes with that status, so
    the hierarchy scim2-models exposes is extended with it.
    """

    status = HTTPStatus.REQUEST_ENTITY_TOO_LARGE


class PreconditionFailedException(SCIMException):
    """An operation whose expected version is not the resource's current one.

    :rfc:`RFC7644 §3.12 <7644#section-3.12>`, Table 8, "412 (Precondition
    Failed)": "Failed to update. Resource has changed on the server." No
    scimType of Table 9 goes with that status, so the hierarchy scim2-models
    exposes is extended with it.
    """

    status = HTTPStatus.PRECONDITION_FAILED


class NotFoundException(SCIMException):
    """A bulk operation whose path designates no endpoint or resource.

    :rfc:`RFC7644 §3.12 <7644#section-3.12>`, Table 8, "404 (Not Found)":
    "Specified resource (e.g., User) or endpoint does not exist." No
    scimType of Table 9 goes with that status, so the hierarchy scim2-models
    exposes is extended with it.
    """

    status = HTTPStatus.NOT_FOUND


class NotImplementedException(SCIMException):
    """An operation the service provider does not announce.

    :rfc:`RFC7644 §3.12 <7644#section-3.12>`, Table 8, "501 (Not
    Implemented)": "Service provider does not support the request
    operation, e.g., PATCH." No scimType of Table 9 goes with that status,
    so the hierarchy scim2-models exposes is extended with it.
    """

    status = HTTPStatus.NOT_IMPLEMENTED


class SCIM2:
    """Flask extension exposing a SCIM 2.0 server backed by a :class:`ScimStorage`.

    The :class:`~scim2_models.ScimProvider` describes the service: the
    resource types it serves, the configuration it announces, and the policy
    the extension applies when it reads and writes payloads.

    Usage::

        storage = MyStorage()
        scim2 = SCIM2(storage, ScimProvider(models=[User]))
        scim2.init_app(app)

    Or with the application factory pattern::

        scim2 = SCIM2(storage, ScimProvider(models=[User]))


        def create_app():
            app = Flask(__name__)
            scim2.init_app(app)
            return app

    Subclass :class:`SCIM2` and override its methods to customize behavior,
    such as the resource location URL.

    :param storage: The storage the extension reads and writes resources in.
    :param provider: The service description. It must declare at least one
        resource type.
    :param app: The application to register on right away, if any.
    :param url_prefix: The URL prefix the SCIM endpoints are served under.
    :param name: The name of the blueprint, and so the prefix of its
        endpoints. Give each instance its own name to serve several SCIM
        servers from one application.
    """

    def __init__(
        self,
        storage: ScimStorage,
        provider: ScimProvider,
        app: Flask | None = None,
        *,
        url_prefix: str = "/scim/v2",
        name: str = "scim2",
    ) -> None:
        if not provider.resource_types:
            raise ValueError("SCIM2 extension requires at least one resource type")

        self.storage = storage
        self.provider = provider
        self.url_prefix = url_prefix
        self.name = name

        if app is not None:
            self.init_app(app)

    def init_app(self, app: Flask) -> None:
        """Register the SCIM blueprint on ``app``, under ``url_prefix``.

        The extension is then available as ``app.extensions["scim2"][name]``.
        """
        blueprint = self.create_blueprint()
        app.register_blueprint(blueprint)
        app.extensions.setdefault(EXTENSION_NAME, {})[self.name] = self

    def create_blueprint(self) -> Blueprint:
        """Return the :class:`~flask.Blueprint` serving the SCIM endpoints.

        It holds the resource, search, discovery and bulk endpoints of every
        resource type the provider declares, and the error handlers turning
        failures into SCIM :class:`~scim2_models.Error` payloads.
        """
        blueprint = Blueprint(self.name, __name__, url_prefix=self.url_prefix)

        # Payloads are read and written under the provider, and so under the
        # policy it declares.
        @blueprint.before_request
        def _enter_provider() -> None:
            self.provider.__enter__()
            g.scim2_provider_entered = True

        @blueprint.teardown_request
        def _exit_provider(_error: BaseException | None) -> None:
            if g.pop("scim2_provider_entered", False):
                self.provider.__exit__(None, None, None)

        @blueprint.after_request
        def _set_content_type(response: Response) -> Response:
            response.headers["Content-Type"] = "application/scim+json"
            return response

        blueprint.register_error_handler(ValidationError, self._handle_validation_error)
        blueprint.register_error_handler(SCIMException, self._handle_scim_exception)
        blueprint.register_error_handler(HTTPException, self._handle_http_exception)

        for resource_type in self.provider.resource_types:
            self._register_resource_routes(blueprint, resource_type)

        self._register_discovery_routes(blueprint)
        self._register_bulk_route(blueprint)

        def me_view() -> Any:
            # RFC7644 §3.11: "A service provider that does NOT support
            # this feature SHOULD respond with HTTP status code 501 (Not
            # Implemented)."
            raise HTTPNotImplemented("/Me is not supported")

        blueprint.add_url_rule(
            "/Me", "me", me_view, methods=["GET", "POST", "PUT", "PATCH", "DELETE"]
        )

        def not_found_view(_path: str) -> Any:
            # This route also catches the methods another route does not
            # support, which Werkzeug would otherwise answer with a 405.
            adapter = cast(MapAdapter, current_app.create_url_adapter(request))
            allowed = [
                method
                for method in ("GET", "POST", "PUT", "PATCH", "DELETE")
                if adapter.match(method=method)[0] != request.endpoint
            ]
            if allowed:
                raise MethodNotAllowed(valid_methods=allowed)
            raise NotFound()

        blueprint.add_url_rule(
            "/<path:_path>",
            "not_found",
            not_found_view,
            methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        )

        return blueprint

    # -- Overridable hooks -------------------------------------------

    def get_service_provider_config(self) -> ServiceProviderConfig:
        """Return the server's :class:`~scim2_models.ServiceProviderConfig`.

        This is the configuration the provider carries, if any. Give the
        provider one, or override this method, to advertise the features
        your :class:`ScimStorage` actually supports.
        """
        if self.provider.config is not None:
            return self.provider.config
        return ServiceProviderConfig(
            patch=Patch(supported=True),
            bulk=Bulk(supported=False, max_operations=0, max_payload_size=0),
            filter=Filter(supported=False, max_results=None),
            change_password=ChangePassword(supported=False),
            sort=Sort(supported=False),
            etag=ETag(supported=False),
            authentication_schemes=[],
        )

    def resource_location(self, resource_type: ResourceType, resource_id: str) -> str:
        """Return the canonical URL of the resource identified by ``resource_id``.

        Every ``meta.location`` and bulk operation ``location`` is built here.
        """
        slug = self._slug(resource_type)
        return url_for(
            f"{self.name}.get_{slug}", resource_id=resource_id, _external=True
        )

    # -- Error responses ---------------------------------------------

    def _handle_validation_error(
        self, error: ValidationError
    ) -> tuple[dict[str, Any], int]:
        """Turn an invalid payload into a SCIM error response.

        The response reports only the first validation error: the SCIM
        Error resource (RFC7644 §3.12) carries a single detail and
        scimType, not a list of errors.
        """
        scim_error = Error.from_validation_error(error.errors()[0])
        assert scim_error.status is not None
        return scim_error.model_dump(), scim_error.status

    def _handle_scim_exception(
        self, error: SCIMException
    ) -> tuple[dict[str, Any], int]:
        """Turn a SCIMException into a SCIM error response."""
        scim_error = error.to_error()
        assert scim_error.status is not None
        return scim_error.model_dump(), scim_error.status

    def _handle_http_exception(
        self, error: HTTPException
    ) -> tuple[dict[str, Any], int, list[tuple[str, str]]]:
        """Turn a Werkzeug HTTPException into a SCIM error response."""
        scim_error = Error(status=error.code, detail=error.description)
        return scim_error.model_dump(), error.code or 500, error.get_headers()

    # -- Resource types ----------------------------------------------

    def _model(self, resource_type: ResourceType) -> type[Resource[Any]]:
        """Return the model validating the resources of `resource_type`."""
        return cast(type[Resource[Any]], self.provider.model_for(resource_type))

    def _endpoint(self, resource_type: ResourceType) -> str:
        return str(resource_type.endpoint).lstrip("/")

    def _slug(self, resource_type: ResourceType) -> str:
        return str(resource_type.id).lower()

    def _resource_union(self) -> Any:
        # Resource types sharing a schema share a model, listed once.
        models = dict.fromkeys(map(self._model, self.provider.resource_types))
        return reduce(or_, models)

    def _resource_type_of(self, resource: Resource[Any]) -> ResourceType:
        """Return the resource type a resource from the storage belongs to.

        The storage records it in `meta.resourceType`, since two resource
        types may share a model.
        """
        name = resource.meta.resource_type if resource.meta else None
        for resource_type in self.provider.resource_types:
            if name is not None and resource_type.name == name:
                return resource_type
        raise ValueError(
            f"The storage returned a resource whose meta.resourceType, {name!r}, "
            "names no resource type the provider declares"
        )

    def _resource_type_at(self, endpoint: str) -> ResourceType | None:
        key = endpoint.lstrip("/").casefold()
        for resource_type in self.provider.resource_types:
            if self._endpoint(resource_type).casefold() == key:
                return resource_type
        return None

    # -- Routes ------------------------------------------------------

    def _register_resource_routes(
        self, blueprint: Blueprint, resource_type: ResourceType
    ) -> None:
        endpoint = self._endpoint(resource_type)
        slug = self._slug(resource_type)
        model = self._model(resource_type)

        def search(search_request: SearchRequest[Any], scim_ctx: Context) -> Any:
            self._check_filter_supported(search_request)
            total, resources = self.storage.search([resource_type], search_request)
            for resource in resources:
                self._with_meta(resource_type, resource)
            response = _parametrize(ListResponse, model)(
                total_results=total,
                start_index=search_request.start_index or 1,
                items_per_page=len(resources),
                resources=resources,
            )
            return response.model_dump(
                scim_ctx=scim_ctx,
                response_parameters=search_request,
            )

        def list_view() -> Any:
            search_request = _parametrize(SearchRequest, model).model_validate(
                request.args.to_dict()
            )
            return search(search_request, Context.RESOURCE_QUERY_RESPONSE)

        def search_view() -> Any:
            search_request = _parametrize(SearchRequest, model).model_validate_json(
                request.data, scim_ctx=Context.SEARCH_REQUEST
            )
            return search(search_request, Context.SEARCH_RESPONSE)

        def create_view() -> Any:
            response_parameters: ResponseParameters[Any] = (
                ResponseParameters.model_validate(request.args.to_dict())
            )
            payload = model.model_validate_json(
                request.data, scim_ctx=Context.RESOURCE_CREATION_REQUEST
            )
            created = self.storage.create(resource_type, payload)
            return self._resource_response(
                resource_type,
                created,
                {
                    "scim_ctx": Context.RESOURCE_CREATION_RESPONSE,
                    "response_parameters": response_parameters,
                },
                HTTPStatus.CREATED,
            )

        def get_view(resource_id: str) -> Any:
            response_parameters: ResponseParameters[Any] = (
                ResponseParameters.model_validate(request.args.to_dict())
            )
            resource = self.storage.query(resource_type, resource_id)
            return self._resource_response(
                resource_type,
                resource,
                {
                    "scim_ctx": Context.RESOURCE_QUERY_RESPONSE,
                    "response_parameters": response_parameters,
                },
            )

        blueprint.add_url_rule(
            f"/{endpoint}", f"list_{slug}", list_view, methods=["GET"]
        )
        blueprint.add_url_rule(
            f"/{endpoint}", f"create_{slug}", create_view, methods=["POST"]
        )
        blueprint.add_url_rule(
            f"/{endpoint}/<resource_id>", f"get_{slug}", get_view, methods=["GET"]
        )
        blueprint.add_url_rule(
            f"/{endpoint}/.search", f"search_{slug}", search_view, methods=["POST"]
        )

        def replace_view(resource_id: str) -> Any:
            response_parameters: ResponseParameters[Any] = (
                ResponseParameters.model_validate(request.args.to_dict())
            )
            payload = model.model_validate_json(
                request.data, scim_ctx=Context.RESOURCE_REPLACEMENT_REQUEST
            )
            updated = self._replace(
                resource_type, resource_id, payload, request.if_match
            )
            return self._resource_response(
                resource_type,
                updated,
                {
                    "scim_ctx": Context.RESOURCE_REPLACEMENT_RESPONSE,
                    "response_parameters": response_parameters,
                },
            )

        def patch_view(resource_id: str) -> Any:
            response_parameters: ResponseParameters[Any] = (
                ResponseParameters.model_validate(request.args.to_dict())
            )
            patch_op = _parametrize(PatchOp, model).model_validate_json(
                request.data, scim_ctx=Context.RESOURCE_PATCH_REQUEST
            )
            patched = self._patch(
                resource_type, resource_id, patch_op, request.if_match
            )
            return self._resource_response(
                resource_type,
                patched,
                {
                    "scim_ctx": Context.RESOURCE_PATCH_RESPONSE,
                    "response_parameters": response_parameters,
                },
            )

        def delete_view(resource_id: str) -> Any:
            self._delete(resource_type, resource_id, request.if_match)
            return "", HTTPStatus.NO_CONTENT

        blueprint.add_url_rule(
            f"/{endpoint}/<resource_id>",
            f"replace_{slug}",
            replace_view,
            methods=["PUT"],
        )
        blueprint.add_url_rule(
            f"/{endpoint}/<resource_id>", f"patch_{slug}", patch_view, methods=["PATCH"]
        )
        blueprint.add_url_rule(
            f"/{endpoint}/<resource_id>",
            f"delete_{slug}",
            delete_view,
            methods=["DELETE"],
        )

    def _register_discovery_routes(self, blueprint: Blueprint) -> None:
        def _reject_filter() -> None:
            """RFC7644 §4.

            "Query parameters described in Section 3.4.2, such as
            filtering, sorting, and pagination, SHALL be ignored. If a
            "filter" is provided, the service provider SHOULD respond
            with HTTP status code 403 (Forbidden) to ensure that clients
            cannot incorrectly assume that any matching conditions
            specified in a filter are true."
            """
            if request.args.get("filter"):
                raise Forbidden("Discovery endpoints do not support filtering")

        @blueprint.get("/ServiceProviderConfig")
        def service_provider_config() -> Any:
            _reject_filter()
            return self.get_service_provider_config().model_dump(
                scim_ctx=Context.RESOURCE_QUERY_RESPONSE
            )

        @blueprint.get("/ResourceTypes")
        def list_resource_types() -> Any:
            _reject_filter()
            resource_types = self.provider.resource_types
            response = ListResponse[ResourceType](
                total_results=len(resource_types),
                start_index=1,
                items_per_page=len(resource_types),
                resources=list(resource_types),
            )
            return response.model_dump(scim_ctx=Context.RESOURCE_QUERY_RESPONSE)

        @blueprint.post("/.search")
        def search_root() -> Any:
            resource_union = self._resource_union()
            search_request = _parametrize(
                SearchRequest, resource_union
            ).model_validate_json(request.data, scim_ctx=Context.SEARCH_REQUEST)
            self._check_filter_supported(search_request)
            total, resources = self.storage.search(
                list(self.provider.resource_types), search_request
            )
            for resource in resources:
                self._with_meta(self._resource_type_of(resource), resource)
            response = _parametrize(ListResponse, resource_union)(
                total_results=total,
                start_index=search_request.start_index or 1,
                items_per_page=len(resources),
                resources=resources,
            )
            return response.model_dump(
                scim_ctx=Context.SEARCH_RESPONSE,
                response_parameters=search_request,
            )

        @blueprint.get("/ResourceTypes/<name>")
        def get_resource_type_view(name: str) -> Any:
            for resource_type in self.provider.resource_types:
                if resource_type.id == name:
                    return resource_type.model_dump(
                        scim_ctx=Context.RESOURCE_QUERY_RESPONSE
                    )
            raise NotFound(f"ResourceType {name!r} not found")

        @blueprint.get("/Schemas")
        def list_schemas() -> Any:
            _reject_filter()
            schemas = self.provider.schemas
            response = ListResponse[Schema](
                total_results=len(schemas),
                start_index=1,
                items_per_page=len(schemas),
                resources=list(schemas),
            )
            return response.model_dump(scim_ctx=Context.RESOURCE_QUERY_RESPONSE)

        @blueprint.get("/Schemas/<path:schema_id>")
        def get_schema_view(schema_id: str) -> Any:
            for schema in self.provider.schemas:
                if schema.id == schema_id:
                    return schema.model_dump(scim_ctx=Context.RESOURCE_QUERY_RESPONSE)
            raise NotFound(f"Schema {schema_id!r} not found")

    def _register_bulk_route(self, blueprint: Blueprint) -> None:
        @blueprint.post("/Bulk")
        def bulk() -> Any:
            bulk_config = self.get_service_provider_config().bulk
            if bulk_config is None or not bulk_config.supported:
                raise HTTPNotImplemented("Bulk operations are not supported")
            # RFC7644 §3.7.4: "The service provider MUST define the
            # maximum number of operations and maximum payload size a
            # client may send in a single request. [...] If either limit
            # is exceeded, the service provider MUST return HTTP response
            # code 413 (Payload Too Large)."
            # Werkzeug refuses a body beyond this limit with a 413. A
            # stricter limit of the application is kept.
            if bulk_config.max_payload_size is not None and (
                request.max_content_length is None
                or bulk_config.max_payload_size < request.max_content_length
            ):
                request.max_content_length = bulk_config.max_payload_size

            bulk_request = _parametrize(
                BulkRequest, self._resource_union()
            ).model_validate_json(request.get_data(), scim_ctx=Context.BULK_REQUEST)
            operations = bulk_request.operations or []
            # RFC7644 §3.7.4: "If either limit is exceeded, the service
            # provider MUST return HTTP response code 413 (Payload Too
            # Large)."
            if (
                bulk_config.max_operations is not None
                and len(operations) > bulk_config.max_operations
            ):
                raise PayloadTooLargeException(
                    detail=(
                        "The number of operations exceeds the "
                        f"maxOperations ({bulk_config.max_operations})."
                    )
                )

            results = []
            errors = 0
            for operation in operations:
                self._run_bulk_operation(operation)
                results.append(operation)
                if (
                    operation.status is not None
                    and operation.status < HTTPStatus.BAD_REQUEST
                ):
                    continue
                # RFC7644 §3.7: "The service provider MUST continue
                # performing as many changes as possible and disregard
                # partial failures. The client MAY override this behavior by
                # specifying a value for the "failOnErrors" attribute."
                errors += 1
                if (
                    bulk_request.fail_on_errors
                    and errors >= bulk_request.fail_on_errors
                ):
                    break

            response = _parametrize(BulkResponse, self._resource_union())(
                operations=results
            )
            return response.model_dump(scim_ctx=Context.BULK_RESPONSE)

    # -- Request checks ----------------------------------------------

    def _check_filter_supported(self, search_request: SearchRequest[Any]) -> None:
        """Refuse a filter the service provider does not announce.

        RFC7644 §3.4.2.2: "Providers MUST decline to filter results if the
        specified filter operation is not recognized and return an HTTP 400
        error with a "scimType" error of "invalidFilter" and an appropriate
        human-readable response as per Section 3.12."
        """
        filter_config = self.get_service_provider_config().filter
        if search_request.filter and not (filter_config and filter_config.supported):
            raise InvalidFilterException(
                detail="Filtering is not supported by this service provider."
            )

    def _check_patch_supported(self) -> None:
        """Refuse PATCH if the service provider does not announce it.

        RFC7644 §3.12, Table 8, "501 (Not Implemented)": "Service provider
        does not support the request operation, e.g., PATCH."
        """
        patch_config = self.get_service_provider_config().patch
        if not (patch_config and patch_config.supported):
            raise NotImplementedException(detail="PATCH is not supported")

    def _check_version(self, resource: Resource[Any], if_match: ETags) -> None:
        """Refuse an operation if the client's ETags do not match the resource's version.

        RFC7644 §3.14: "If the service provider supports versioning of
        resources, the client MAY supply an If-Match header (Section 3.1 of
        [RFC7232]) for PUT and PATCH operations to ensure that the requested
        operation succeeds only if the supplied ETag matches the latest
        service provider resource [...]."

        RFC7644 §3.7: "Version MAY be used if the service provider supports
        entity-tags (ETags) (Section 2.3 of [RFC7232]) and "method" is "PUT",
        "PATCH", or "DELETE"."
        """
        if not if_match:
            return
        version = resource.meta.version if resource.meta else None
        if version is None:
            return
        if not if_match.contains_raw(version):
            raise PreconditionFailedException(detail="ETag mismatch")

    # -- Operations --------------------------------------------------

    def _replace(
        self,
        resource_type: ResourceType,
        resource_id: str,
        replacement: Resource[Any],
        if_match: ETags,
    ) -> Resource[Any]:
        """Replace a resource, and return the stored representation."""
        original = self.storage.query(resource_type, resource_id)
        self._check_version(original, if_match)
        replacement.replace(original)
        return self.storage.update(resource_type, replacement)

    def _patch(
        self,
        resource_type: ResourceType,
        resource_id: str,
        patch_op: PatchOp[Any],
        if_match: ETags,
    ) -> Resource[Any]:
        """Patch a resource, and return the stored representation."""
        self._check_patch_supported()
        resource = self.storage.query(resource_type, resource_id)
        self._check_version(resource, if_match)
        if patch_op.patch(resource):
            resource = self.storage.update(resource_type, resource)
        return resource

    def _delete(
        self, resource_type: ResourceType, resource_id: str, if_match: ETags
    ) -> None:
        """Delete a resource.

        The resource is only read to check its version: the storage reports
        a missing one on its own.
        """
        if if_match:
            self._check_version(
                self.storage.query(resource_type, resource_id), if_match
            )
        self.storage.delete(resource_type, resource_id)

    # -- Bulk operations ---------------------------------------------

    def _locate_bulk_resource(
        self, operation: BulkOperation[Any]
    ) -> tuple[ResourceType, str]:
        """Return the resource type and id a bulk PUT, PATCH or DELETE targets.

        The location of the operation is set first, as it is due even if
        the operation fails. RFC7644 §3.7.3: "A "location" attribute that
        includes the resource's endpoint MUST be returned for all operations
        except for failed POST operations (which have no location)."
        """
        path = cast(str, operation.path)
        endpoint, _, resource_id = path.rpartition("/")
        resource_type = self._resource_type_at(endpoint)
        if resource_type is None:
            operation.location = url_for(
                f"{self.name}.not_found", _path=path.lstrip("/"), _external=True
            )
            raise NotFoundException(detail=f"No resource at {path!r}")
        operation.location = self.resource_location(resource_type, resource_id)
        return resource_type, resource_id

    def _run_bulk_operation(self, operation: BulkOperation[Any]) -> None:
        """Apply one bulk operation, and turn it into the description of its outcome."""
        if_match = parse_etags(operation.version)
        operation.version = None

        try:
            if operation.method == BulkOperation.Method.post:
                path = cast(str, operation.path)
                resource_type = self._resource_type_at(path)
                if resource_type is None:
                    raise NotFoundException(detail=f"No endpoint at {path!r}")
                created = self.storage.create(
                    resource_type, cast(Resource[Any], operation.data)
                )
                meta = self._with_meta(resource_type, created)
                operation.status = HTTPStatus.CREATED
                operation.location = meta.location
                operation.version = meta.version

            elif operation.method == BulkOperation.Method.put:
                resource_type, resource_id = self._locate_bulk_resource(operation)
                replaced = self._replace(
                    resource_type,
                    resource_id,
                    cast(Resource[Any], operation.data),
                    if_match,
                )
                operation.status = HTTPStatus.OK
                operation.version = self._with_meta(resource_type, replaced).version

            elif operation.method == BulkOperation.Method.patch:
                resource_type, resource_id = self._locate_bulk_resource(operation)
                patched = self._patch(
                    resource_type,
                    resource_id,
                    cast("PatchOp[Any]", operation.data),
                    if_match,
                )
                operation.status = HTTPStatus.OK
                operation.version = self._with_meta(resource_type, patched).version

            elif operation.method == BulkOperation.Method.delete:
                resource_type, resource_id = self._locate_bulk_resource(operation)
                self._delete(resource_type, resource_id, if_match)
                operation.status = HTTPStatus.NO_CONTENT

        except SCIMException as exc:
            operation.status = exc.status
            operation.response = exc.to_error()

    # -- Responses ---------------------------------------------------

    def _with_meta(self, resource_type: ResourceType, resource: Resource[Any]) -> Meta:
        """Check the `meta` of a resource from the storage, complete it, and return it."""
        if resource.meta is None or resource.meta.resource_type != resource_type.name:
            name = resource.meta.resource_type if resource.meta else None
            raise ValueError(
                f"The storage returned a {resource_type.name} resource whose "
                f"meta.resourceType is {name!r}"
            )
        assert resource.id is not None
        resource.meta.location = self.resource_location(resource_type, resource.id)
        return resource.meta

    def _resource_response(
        self,
        resource_type: ResourceType,
        resource: Resource[Any],
        dump_kwargs: dict[str, Any],
        status: int = HTTPStatus.OK,
    ) -> WerkzeugResponse:
        """Build a single-resource response.

        RFC7643 §3.1: "location The URI of the resource being returned. This
        value MUST be the same as the "Content-Location" HTTP response header
        (see Section 3.1.4.2 of [RFC7231])."

        RFC7644 §3.3: "The URI of the created resource SHALL include, in the
        HTTP "Location" header and the HTTP body, a JSON representation
        [RFC7159] with the attribute "meta.location"."

        RFC7644 §3.14: "When supported, SCIM ETags MUST be specified as an
        HTTP header and SHOULD be specified within the 'version' attribute
        contained in the resource's 'meta' attribute."
        """
        meta = self._with_meta(resource_type, resource)
        response = jsonify(resource.model_dump(**dump_kwargs))
        response.status_code = status
        response.headers["Content-Location"] = meta.location
        if status == HTTPStatus.CREATED:
            response.headers["Location"] = meta.location
        if meta.version:
            response.headers["ETag"] = meta.version
        # Answers a GET carrying a matching If-None-Match with a 304.
        return response.make_conditional(request)
