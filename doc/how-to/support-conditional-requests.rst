Support conditional requests
============================

Use this guide to let clients detect concurrent changes with ETags
(:rfc:`RFC7644 §3.14 <7644#section-3.14>`). A client then reads a resource only when it changed,
and modifies it only when nobody else did in the meantime.

Give each resource a version
----------------------------

Set ``meta.version`` on every resource the storage creates or updates. The value must change
whenever the resource changes. The tutorial storage computes a weak ETag from the content:

.. literalinclude:: ../../examples/minimal_server.py
   :language: python
   :pyobject: make_etag

Then announce the feature with ``etag=ETag(supported=True)`` in the
:class:`~scim2_models.ServiceProviderConfig`, as :doc:`announce-supported-features` shows.
Without it, the extension ignores the versions.

Check the result
----------------

The extension then sends the version in the ``ETag`` header of every resource response:

.. doctest::

   >>> from flask import Flask
   >>> from scim2_flask import SCIM2
   >>> app = Flask(__name__)
   >>> scim2 = SCIM2(InMemoryStorage(), create_provider(), app=app)
   >>> client = app.test_client()
   >>> headers = {"Content-Type": "application/scim+json"}
   >>> response = client.post(
   ...     "/scim/v2/Users",
   ...     json={"schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"], "userName": "bjensen"},
   ...     headers=headers,
   ... )
   >>> etag = response.headers["ETag"]
   >>> location = response.json["meta"]["location"]

It answers ``304`` to a ``GET`` whose ``If-None-Match`` holds the current version:

.. doctest::

   >>> client.get(location, headers={"If-None-Match": etag}).status_code
   304

It answers ``412`` to a ``PUT``, ``PATCH`` or ``DELETE`` whose ``If-Match`` holds another
version:

.. doctest::

   >>> client.delete(location, headers={"If-Match": 'W/"outdated"'}).status_code
   412

In a bulk request, the extension compares the ``version`` of each operation the same way.
