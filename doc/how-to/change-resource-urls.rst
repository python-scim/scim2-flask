Change the resource URLs
========================

Use this guide when the SCIM endpoints must live under another path, or when clients reach the
server through a URL the application does not see, such as behind a reverse proxy.

Change the prefix
-----------------

The extension serves the endpoints under ``/scim/v2`` by default. Pass another ``url_prefix``:

.. doctest::

   >>> from flask import Flask
   >>> from scim2_flask import SCIM2
   >>> app = Flask(__name__)
   >>> scim2 = SCIM2(InMemoryStorage(), create_provider(), app=app, url_prefix="/api/scim")
   >>> app.test_client().get("/api/scim/Users").status_code
   200

Serve several SCIM servers
--------------------------

To serve several SCIM servers from one application, such as one per tenant, give each instance
its own prefix and its own ``name``. The name is the one of the blueprint, and the key of the
instance in ``app.extensions["scim2"]``:

.. doctest::

   >>> app = Flask(__name__)
   >>> tenant_a = SCIM2(InMemoryStorage(), create_provider(), app=app, url_prefix="/a/scim/v2", name="tenant_a")
   >>> tenant_b = SCIM2(InMemoryStorage(), create_provider(), app=app, url_prefix="/b/scim/v2", name="tenant_b")
   >>> app.extensions["scim2"]["tenant_b"] is tenant_b
   True

Change the location of the resources
------------------------------------

The extension builds every ``meta.location``, ``Location`` header and bulk ``location`` with
:meth:`~scim2_flask.SCIM2.resource_location`. Override it to return the URL clients use:

.. doctest::

   >>> class PublicSCIM2(SCIM2):
   ...     def resource_location(self, resource_type, resource_id):
   ...         return f"https://scim.example.org/v2{resource_type.endpoint}/{resource_id}"
   >>> app = Flask(__name__)
   >>> scim2 = PublicSCIM2(InMemoryStorage(), create_provider(), app=app)
   >>> response = app.test_client().post(
   ...     "/scim/v2/Users",
   ...     json={"schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"], "userName": "bjensen"},
   ...     headers={"Content-Type": "application/scim+json"},
   ... )
   >>> response.json["meta"]["location"]
   'https://scim.example.org/v2/Users/...'

Behind a reverse proxy, Werkzeug's :class:`~werkzeug.middleware.proxy_fix.ProxyFix` is an
alternative: it makes the generated URLs use the host and scheme the proxy received.
