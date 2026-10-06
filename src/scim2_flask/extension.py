from __future__ import annotations

import json
from http import HTTPStatus
from typing import Any

from flask import Blueprint
from flask import Flask
from flask import Response
from flask import request
from flask import url_for
from scim2_models import Error
from scim2_models import SCIMException
from scim2_models import ScimProvider
from scim2_server.handler import ScimHandler
from scim2_server.requests import ScimRequest
from scim2_server.responses import ScimResponse
from scim2_server.routing import ROUTES
from scim2_server.routing import Route
from scim2_server.service import ScimService
from scim2_server.storage import ScimStorage
from werkzeug.exceptions import HTTPException

EXTENSION_NAME = "scim"

METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]


class ScimServer:
    """Flask extension exposing a SCIM 2.0 server backed by a :class:`~scim2_server.storage.ScimStorage`.

    The :class:`~scim2_models.ScimProvider` describes the service: the
    resource types it serves, the configuration it announces, and the policy
    the extension applies when it reads and writes payloads.

    Usage::

        storage = MyStorage()
        scim_server = ScimServer(storage, ScimProvider(models=[User]))
        scim_server.init_app(app)

    Or with the application factory pattern::

        scim_server = ScimServer(storage, ScimProvider(models=[User]))


        def create_app():
            app = Flask(__name__)
            scim_server.init_app(app)
            return app

    :param storage: The storage the extension reads and writes resources in.
    :param provider: The service description. It must declare at least one
        resource type.
    :param app: The application to register on right away, if any.
    :param service: The service serving the requests, built upon ``provider``.
        Pass a subclass of :class:`~scim2_server.service.ScimService` to change
        one of its steps, such as the URL of the resources.
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
        service: ScimService | None = None,
        url_prefix: str = "/scim/v2",
        name: str = "scim",
    ) -> None:
        if not provider.resource_types:
            raise ValueError("ScimServer requires at least one resource type")

        self.storage = storage
        self.provider = provider
        self.service = service if service is not None else ScimService(provider)
        self.handler = ScimHandler(self.service, storage)
        self.url_prefix = url_prefix.rstrip("/")
        self.name = name

        if app is not None:
            self.init_app(app)

    def init_app(self, app: Flask) -> None:
        """Register the SCIM blueprint on ``app``, under ``url_prefix``.

        The extension is then available in the ``"scim"`` entry of
        :attr:`~flask.Flask.extensions`, under its ``name``.
        """
        app.register_blueprint(self.create_blueprint())
        app.extensions.setdefault(EXTENSION_NAME, {})[self.name] = self

    def create_blueprint(self) -> Blueprint:
        """Return the :class:`~flask.Blueprint` serving the SCIM endpoints.

        It has one endpoint per route of :data:`~scim2_server.routing.ROUTES`,
        named after the route, such as ``scim.query``, whose arguments are
        ``resource_endpoint`` and ``resource_id``. A ``fallback`` endpoint
        answers the other requests with a SCIM error.
        """
        blueprint = Blueprint(self.name, __name__, url_prefix=self.url_prefix)
        blueprint.register_error_handler(SCIMException, self._handle_scim_exception)
        blueprint.register_error_handler(HTTPException, self._handle_http_exception)

        for route in ROUTES:
            blueprint.add_url_rule(
                flask_rule(route),
                route.name,
                self._make_view(route),
                methods=[route.method],
            )

        blueprint.add_url_rule(
            "/", "fallback", self._fallback_view, methods=METHODS, defaults={"path": ""}
        )
        blueprint.add_url_rule(
            "/<path:path>", "fallback", self._fallback_view, methods=METHODS
        )
        return blueprint

    def get_subject(self) -> Any:
        """Return the authenticated subject of the current request.

        It returns :data:`None` by default. Override it to pass the subject
        your application authenticated to the service, for
        :meth:`~scim2_server.service.ScimService.authorize` and ``/Me``.
        """
        return None

    def _make_view(self, route: Route) -> Any:
        method = getattr(self.handler, route.operation.value)

        def view(**_kwargs: str) -> Response:
            return self._to_response(method(self.read_request()))

        return view

    def _fallback_view(self, path: str) -> Response:
        return self._to_response(self.handler.handle(self.read_request()))

    def read_request(self) -> ScimRequest:
        """Return the :class:`~scim2_server.requests.ScimRequest` of the current Flask request."""
        scim_request = ScimRequest(
            method=request.method,
            base_url=url_for(f"{self.name}.search_root", _external=True).rstrip("/"),
            path=request.path.removeprefix(self.url_prefix),
            query=request.args.to_dict(),
            headers=list(request.headers.items()),
            subject=self.get_subject(),
        )
        scim_request.body = self.read_body(scim_request)
        return scim_request

    def read_body(self, scim_request: ScimRequest) -> bytes:
        """Read the body of the current request, up to one byte more than the service accepts.

        The service answers a larger body with a 413. The :data:`~flask:MAX_CONTENT_LENGTH`
        of the application still applies.
        """
        limit = self.service.max_body_size(scim_request)
        if limit is None:
            return request.get_data()
        body: bytes = request.stream.read(limit + 1)
        return body

    @staticmethod
    def _to_response(scim_response: ScimResponse) -> Response:
        body = (
            json.dumps(scim_response.body) if scim_response.body is not None else None
        )
        return Response(
            body, status=scim_response.status, headers=scim_response.headers
        )

    def _handle_scim_exception(self, exception: SCIMException) -> Response:
        return self._to_response(self.service.error_response(exception))

    def _handle_http_exception(self, exception: HTTPException) -> Response:
        """Turn a Werkzeug exception, such as one raised by a hook of the application, into a SCIM error."""
        error = Error(status=exception.code, detail=exception.description)
        response = self._to_response(
            ScimResponse(HTTPStatus(exception.code or 500), error.model_dump())
        )
        for key, value in exception.get_headers():
            if key.lower() != "content-type":
                response.headers[key] = value
        return response


def flask_rule(route: Route) -> str:
    """Return the Flask rule of a route of :data:`~scim2_server.routing.ROUTES`.

    The endpoint placeholder is renamed, as ``endpoint`` is the first
    argument of :func:`~flask.url_for`.
    """
    return route.pattern.replace("{endpoint}", "<resource_endpoint>").replace(
        "{resource_id}", "<resource_id>"
    )
