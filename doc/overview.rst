Overview
========

scim2-flask serves the **System for Cross-domain Identity Management** (**SCIM**) protocol from a
Flask application. It exposes the endpoints of :rfc:`RFC 7644 <7644>` in a
:class:`~flask.Blueprint`, and leaves the protocol to :doc:`scim2-server <scim2_server:index>` and
the payloads to :doc:`scim2-models <scim2_models:index>`.

It does not keep the resources, nor authenticate the clients: a storage and the Flask application
that registers the extension do.

Install scim2-flask. It brings Flask, scim2-server and scim2-models along:

.. code-block:: console

   $ pip install scim2-flask

This page introduces the parts of a SCIM server built with Flask, in the order an application
meets them. Follow it in order for a first tour. :doc:`integrate` covers the authentication, the
transactions, the URLs and the size of the requests, and the :doc:`reference` lists the complete
API.

Describe the service
--------------------

A :class:`~scim2_models.ScimProvider` describes the service: the resources it serves, and the
features it supports. The following service serves users, with the enterprise extension, and
groups. It supports PATCH, bulk requests, filtering, sorting and ETags:

.. literalinclude:: ../examples/minimal_server.py
   :language: python
   :pyobject: create_provider

Announce filtering, sorting and ETags only when the storage implements them.
:doc:`scim2_models:how-to/describe-a-scim-service` describes the provider in full.

Serve the endpoints
-------------------

The :class:`~scim2_flask.ScimServer` extension serves the SCIM endpoints of a provider over a storage.
:class:`~scim2_server.memory.InMemoryStorage` keeps the resources in memory, until the process
stops:

.. doctest::

   >>> from flask import Flask
   >>> from scim2_server.memory import InMemoryStorage
   >>> from examples.minimal_server import create_provider
   >>> from scim2_flask import ScimServer
   >>> app = Flask(__name__)
   >>> scim_server = ScimServer(InMemoryStorage(), create_provider(), app=app)

The endpoints live under ``/scim/v2``. To serve the resources of your own database, write a
storage as :doc:`scim2_server:how-to/write-a-storage` describes, or
:doc:`scim2_server:how-to/serve-an-existing-data-model` for tables the application already has.
Pass it in place of the in-memory one.

Serve a request
---------------

The application now answers SCIM requests. The examples send them with the
:meth:`test client <flask.Flask.test_client>` of Flask, which simulates HTTP requests without
running a server. Create a user, and read it back at its location:

.. doctest::

   >>> client = app.test_client()
   >>> response = client.post(
   ...     "/scim/v2/Users",
   ...     json={"schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"], "userName": "bjensen"},
   ... )
   >>> response.status_code
   201
   >>> user = response.json
   >>> user["meta"]["location"]
   'http://localhost/scim/v2/Users/...'
   >>> client.get(user["meta"]["location"]).json["userName"]
   'bjensen'

A request the server refuses gets a SCIM error:

.. doctest::

   >>> response = client.get("/scim/v2/Users/unknown")
   >>> response.status_code, response.json["schemas"]
   (404, ['urn:ietf:params:scim:api:messages:2.0:Error'])

Run the server
--------------

`examples/minimal_server.py <https://github.com/python-scim/scim2-flask/blob/main/examples/minimal_server.py>`_
gathers these steps in an :doc:`application factory <flask:patterns/appfactories>`:

.. literalinclude:: ../examples/minimal_server.py
   :language: python
   :pyobject: create_app

Run it with the :doc:`Flask command <flask:cli>`, from the directory of the file:

.. code-block:: console

   $ flask --app minimal_server run

Any SCIM client can then reach it at ``http://localhost:5000/scim/v2``, such as
:doc:`scim2-cli <scim2_cli:index>`.

Check a server
--------------

:doc:`scim2-tester <scim2_tester:index>` checks that a SCIM server complies with the RFCs. Its
:func:`~scim2_tester.check_server` function sends the requests an identity provider would send,
and checks each response. The WSGI engine of :doc:`scim2-client <scim2_client:index>` calls the
application directly, without a network:

.. code-block:: console

   $ pip install scim2-tester

.. doctest::

   >>> from scim2_client.engines.wsgi import WSGISCIMClient
   >>> from scim2_tester import check_server
   >>> scim_client = WSGISCIMClient(app, base_url="http://localhost/scim/v2")
   >>> scim_client.discover()
   >>> results = check_server(scim_client)
   >>> [result.title for result in results if result.status.name in ("ERROR", "CRITICAL")]
   []
