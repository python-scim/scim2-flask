Protect the endpoints
=====================

Use this guide to restrict the SCIM endpoints to authenticated clients. The extension leaves
every endpoint open, and lets the application check the credentials. Write the check yourself, or
delegate it to a library such as :ref:`Authlib <authlib-check>`.

Write your own check
---------------------

Subclass :class:`~scim2_flask.SCIM2`, and add a ``before_request`` hook to the blueprint it
creates. The hook runs before every SCIM request, and only before them. Raise a Werkzeug
:class:`~werkzeug.exceptions.Unauthorized` to refuse a request, and name the scheme the server
expects in its ``www_authenticate``:

.. doctest::

   >>> from flask import Flask, request
   >>> from werkzeug.datastructures import WWWAuthenticate
   >>> from werkzeug.exceptions import Unauthorized
   >>> from scim2_flask import SCIM2
   >>> def check_token():
   ...     if request.headers.get("Authorization") != "Bearer secret":
   ...         raise Unauthorized(
   ...             "Missing or invalid token", www_authenticate=WWWAuthenticate("Bearer")
   ...         )
   >>> class ProtectedSCIM2(SCIM2):
   ...     def create_blueprint(self):
   ...         blueprint = super().create_blueprint()
   ...         blueprint.before_request(check_token)
   ...         return blueprint
   >>> app = Flask(__name__)
   >>> scim2 = ProtectedSCIM2(InMemoryStorage(), create_provider(), app=app)

Replace ``check_token`` with the check your application needs, such as the validation of an
OAuth 2.0 bearer token.

The client receives a SCIM error, and the ``WWW-Authenticate`` header naming the scheme.
:rfc:`RFC7644 §2 <7644#section-2>`: "As per Section 4.1 of [RFC7235], a SCIM service provider
SHALL indicate supported HTTP authentication schemes via the "WWW-Authenticate" header."

.. doctest::

   >>> client = app.test_client()
   >>> response = client.get("/scim/v2/Users")
   >>> response.status_code
   401
   >>> response.headers["WWW-Authenticate"]
   'Bearer'
   >>> response.json["detail"]
   'Missing or invalid token'
   >>> client.get("/scim/v2/Users", headers={"Authorization": "Bearer secret"}).status_code
   200

.. _authlib-check:

Validate OAuth 2.0 tokens with Authlib
---------------------------------------

`Authlib <https://docs.authlib.org>`_ validates OAuth 2.0 bearer tokens for you, instead of the
hand-written check above. Install it with ``pip install authlib``.

scim2-flask generates its views itself, so check the token from the ``before_request`` hook, with
a ``with require_oauth.acquire():`` statement, to protect every SCIM endpoint with a single check.
See Authlib's own :ref:`guide on protecting resources <authlib:flask_oauth2_resource_protector>`
for more.

Register a :class:`~authlib.oauth2.rfc6750.BearerTokenValidator` that looks up tokens in your
storage:

.. doctest::

   >>> from dataclasses import dataclass
   >>> from authlib.integrations.flask_oauth2 import ResourceProtector
   >>> from authlib.oauth2.rfc6750 import BearerTokenValidator
   >>> @dataclass
   ... class Token:
   ...     scope: str = ""
   ...     def is_expired(self):
   ...         return False
   ...     def is_revoked(self):
   ...         return False
   ...     def get_scope(self):
   ...         return self.scope
   >>> TOKENS = {"secret": Token()}
   >>> class MyBearerTokenValidator(BearerTokenValidator):
   ...     def authenticate_token(self, token_string):
   ...         return TOKENS.get(token_string)
   >>> require_oauth = ResourceProtector()
   >>> require_oauth.register_token_validator(MyBearerTokenValidator())
   >>> def check_oauth_token():
   ...     with require_oauth.acquire():
   ...         pass
   >>> class OAuthProtectedSCIM2(SCIM2):
   ...     def create_blueprint(self):
   ...         blueprint = super().create_blueprint()
   ...         blueprint.before_request(check_oauth_token)
   ...         return blueprint
   >>> app = Flask(__name__)
   >>> scim2 = OAuthProtectedSCIM2(InMemoryStorage(), create_provider(), app=app)

Replace ``Token`` and ``authenticate_token`` with your real token storage; Authlib's own
:ref:`authlib:flask_oauth2_server` guide describes how to issue the tokens checked here. The
validated token is then available as
:data:`~authlib.integrations.flask_oauth2.current_token` for the rest of the request.

Announce the scheme
-------------------

Describe the authentication scheme in the ``authentication_schemes`` of the
:class:`~scim2_models.ServiceProviderConfig`, so that clients know which credentials to send
(:rfc:`RFC7643 §5 <7643#section-5>`). See :doc:`announce-supported-features`.
