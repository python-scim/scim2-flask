"""Authenticate the clients of the SCIM endpoints with bearer tokens."""

from typing import Any

from flask import Blueprint
from flask import Flask
from flask import g
from flask import request
from scim2_models import AuthenticationScheme
from scim2_models import ScimProvider
from scim2_models import ServiceProviderConfig
from scim2_models import UnauthorizedException
from scim2_models import User
from scim2_server.memory import InMemoryStorage

from scim2_flask import ScimServer

TOKENS = {"secret": "bjensen"}


class ProtectedScimServer(ScimServer):
    def create_blueprint(self) -> Blueprint:
        blueprint = super().create_blueprint()

        @blueprint.before_request
        def check_token() -> None:
            if request.endpoint == f"{self.name}.service_provider_config":
                return
            token = request.headers.get("Authorization", "").removeprefix("Bearer ")
            if token not in TOKENS:
                raise UnauthorizedException(detail="Missing or invalid token")
            g.client = TOKENS[token]

        return blueprint

    def get_subject(self) -> Any:
        return g.get("client")


def create_provider() -> ScimProvider:
    config = ServiceProviderConfig(
        authentication_schemes=[
            AuthenticationScheme(
                type=AuthenticationScheme.Type.oauthbearertoken,
                name="OAuth Bearer Token",
                description="Authentication with an OAuth 2.0 bearer token",
            )
        ]
    )
    return ScimProvider(models=[User], config=config)


def create_app() -> Flask:
    app = Flask(__name__)
    ProtectedScimServer(InMemoryStorage(), create_provider(), app=app)
    return app
