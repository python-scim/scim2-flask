Integrate with the application
==============================

Use this guide to fit the SCIM endpoints into a Flask application: authenticate the clients,
commit the changes of each request, choose the URLs, page with cursors and limit the size of the
requests. It
assumes a :class:`~scim2_server.storage.ScimStorage` and a :class:`~scim2_models.ScimProvider`,
such as the ones of the :doc:`overview`.

The guide covers the Flask side only. The scim2-server guides cover the rest:

- :doc:`scim2_server:how-to/write-a-storage`, to keep the resources in your own backend;
- :doc:`scim2_server:how-to/authenticate-the-clients`, to limit what each client may do;
- :doc:`scim2_server:how-to/serve-the-me-endpoint`, to serve ``/Me``;
- :doc:`scim2_server:how-to/deploy-the-server`, to serve the resources at other URLs;
- :doc:`scim2_server:how-to/page-with-cursors`, to page with cursors.

The examples come from the
`examples <https://github.com/python-scim/scim2-flask/tree/main/examples>`_ directory, and reuse
the ``create_provider`` function of the overview.

Authenticate the clients
------------------------

Subclass :class:`~scim2_flask.ScimServer`, and add a :meth:`~flask.Blueprint.before_request`
hook to the :class:`~flask.Blueprint` it creates. The hook runs before every SCIM request, and only
before them. Raise :class:`~scim2_models.UnauthorizedException` to refuse a request.

Leave ``/ServiceProviderConfig`` open: per :rfc:`RFC 7643 §5 <7643#section-5>`, clients read the
authentication schemes there before they authenticate. The hook recognizes it with
:attr:`request.endpoint <flask.Request.endpoint>`: its endpoint is ``service_provider_config``,
prefixed with the name of the blueprint.

The extension serves each request with a :class:`~scim2_server.service.ScimService`, which applies
the rules of the protocol. Override :meth:`~scim2_flask.ScimServer.get_subject` to pass what the
hook stored in :data:`~flask.g` to this service, as the *subject* of the request:

.. literalinclude:: ../examples/authentication.py
   :language: python
   :pyobject: ProtectedScimServer

Replace ``TOKENS`` with the validation of the tokens of your application, preferably with a
library dedicated to authentication, such as `Authlib <https://docs.authlib.org>`_.

Announce the scheme in the ``authentication_schemes`` of the
:class:`~scim2_models.ServiceProviderConfig`:

.. code-block:: python

   config = ServiceProviderConfig(
       ...,
       authentication_schemes=[
           AuthenticationScheme(
               type=AuthenticationScheme.Type.oauthbearertoken,
               name="OAuth Bearer Token",
               description="Authentication with an OAuth 2.0 bearer token",
           )
       ],
   )

A refused client receives a SCIM error, with a :mdn:`WWW-Authenticate` header built from the
announced schemes:

.. doctest::

   >>> from examples.authentication import create_app
   >>> client = create_app().test_client()
   >>> response = client.get("/scim/v2/Users")
   >>> response.status_code, response.headers["WWW-Authenticate"]
   (401, 'Bearer realm="SCIM"')
   >>> client.get("/scim/v2/Users", headers={"Authorization": "Bearer secret"}).status_code
   200
   >>> client.get("/scim/v2/ServiceProviderConfig").status_code
   200

The service reads the subject in two methods: :meth:`~scim2_server.service.ScimService.authorize`
accepts or refuses each operation, and :meth:`~scim2_server.service.ScimService.me_target` finds
the resource ``/Me`` stands for. To override them, subclass
:class:`~scim2_server.service.ScimService`, and pass an instance to the ``service`` parameter of
:class:`~scim2_flask.ScimServer`.

Commit the changes of each request
----------------------------------

The extension never commits. It encloses each SCIM operation in the
:meth:`~scim2_server.storage.ScimStorage.operation` context manager of the storage: the request
itself, or each operation of a bulk request. A SQL storage opens a savepoint there, so that a
failed operation of a bulk request does not undo the others.

Commit once per request, in an :meth:`~flask.Blueprint.after_request` hook of the blueprint.
Flask calls the hook for every response: the SCIM errors, and the 500 of an unexpected exception. Commit the responses
below 500, so that the successful operations of a bulk request are kept, and roll back the
others:

.. literalinclude:: ../examples/transactions.py
   :language: python
   :pyobject: TransactionalScimServer

Pass the database session of the application, such as ``db.session`` with
`Flask-SQLAlchemy <https://flask-sqlalchemy.readthedocs.io>`_:

.. code-block:: python

   TransactionalScimServer(storage, provider, session=db.session, app=app)

A commit that fails raises an exception in the hook, and the client receives a 500 rather than a
success.

Choose the URLs
---------------

The extension serves the endpoints under ``/scim/v2`` by default. To serve them under another
path, pass it as ``url_prefix``:

.. doctest::

   >>> from flask import Flask
   >>> from scim2_server.memory import InMemoryStorage
   >>> from examples.minimal_server import create_provider
   >>> from scim2_flask import ScimServer
   >>> app = Flask(__name__)
   >>> scim_server = ScimServer(InMemoryStorage(), create_provider(), app=app, url_prefix="/api/scim")
   >>> app.test_client().get("/api/scim/Users").status_code
   200

To serve several SCIM servers from one application, such as one per tenant, give each instance
its own prefix and its own ``name``. The name is the one of the blueprint, and the key of the
instance in the ``"scim"`` entry of :attr:`~flask.Flask.extensions`:

.. doctest::

   >>> app = Flask(__name__)
   >>> tenant_a = ScimServer(InMemoryStorage(), create_provider(), app=app, url_prefix="/a/scim/v2", name="tenant_a")
   >>> tenant_b = ScimServer(InMemoryStorage(), create_provider(), app=app, url_prefix="/b/scim/v2", name="tenant_b")
   >>> app.extensions["scim"]["tenant_b"] is tenant_b
   True

The blueprint has one Flask endpoint per SCIM route. scim2-server lists these routes in
:data:`~scim2_server.routing.ROUTES`, and each Flask endpoint takes the name of its route, such as
``query`` for ``GET /{endpoint}/{resource_id}``. Build their URLs with :func:`~flask.url_for`. The
path of a resource type, such as ``Users``, is the ``resource_endpoint`` argument:

.. doctest::

   >>> from flask import url_for
   >>> with app.test_request_context():
   ...     url_for("tenant_a.query", resource_endpoint="Users", resource_id="2819c223")
   '/a/scim/v2/Users/2819c223'

The extension builds the URL of each resource from the host the request reached and the
``url_prefix``. Behind a reverse proxy, Werkzeug's :class:`~werkzeug.middleware.proxy_fix.ProxyFix`
makes these URLs use the host and scheme the proxy received, as
:doc:`flask:deploying/proxy_fix` describes.

Page with cursors
-----------------

The server encrypts the cursors with a secret. The extension takes the
:data:`~flask:SECRET_KEY` of the application as this secret. Every process of the application
needs the same one. :meth:`~scim2_flask.ScimServer.init_app` reads it, so load the configuration
first. When the :class:`~scim2_models.ServiceProviderConfig` announces cursor pagination and the
application has no :data:`~flask:SECRET_KEY`, :meth:`~scim2_flask.ScimServer.init_app` raises a
:exc:`ValueError`.

A :class:`~scim2_server.service.ScimService` passed as ``service`` keeps its own secret.

Limit the size of the requests
------------------------------

The :class:`~scim2_models.ServiceProviderConfig` announces ``maxPayloadSize``, the largest body
of a bulk request. The extension reads at most one byte more of a bulk request body, and the
server answers ``413`` beyond it. The extension reads the bodies of the other requests it serves
in full.

To protect the memory of the server, set the :data:`~flask:MAX_CONTENT_LENGTH` setting of Flask.
Keep it above ``maxPayloadSize``: a bulk request within ``maxPayloadSize`` but beyond
:data:`~flask:MAX_CONTENT_LENGTH` gets a ``413`` too. Any request with a larger body gets a
``413``, as a SCIM error:

.. doctest::

   >>> app = Flask(__name__)
   >>> app.config["MAX_CONTENT_LENGTH"] = 2 * 1_048_576
   >>> scim_server = ScimServer(InMemoryStorage(), create_provider(), app=app)
   >>> response = app.test_client().post(
   ...     "/scim/v2/Users",
   ...     data=b"x" * (3 * 1_048_576),
   ...     headers={"Content-Type": "application/scim+json"},
   ... )
   >>> response.status_code, response.headers["Content-Type"]
   (413, 'application/scim+json')
