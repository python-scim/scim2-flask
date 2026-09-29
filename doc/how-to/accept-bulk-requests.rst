Accept bulk requests
====================

Use this guide to let clients send many operations in a single request, with ``POST /Bulk``
(:rfc:`RFC7644 §3.7 <7644#section-3.7>`). The extension runs each operation with the storage
methods it already uses for a single request, so the storage needs nothing more.

Announce the bulk operations
----------------------------

Announce ``bulk`` in the :class:`~scim2_models.ServiceProviderConfig`, with the largest number of
operations and the largest payload, in bytes, the server accepts:

.. doctest::

   >>> from flask import Flask
   >>> from scim2_models import (
   ...     Bulk, ChangePassword, ETag, Filter, Patch, ScimProvider, ServiceProviderConfig,
   ...     Sort, User,
   ... )
   >>> from scim2_flask import SCIM2
   >>> config = ServiceProviderConfig(
   ...     patch=Patch(supported=True),
   ...     bulk=Bulk(supported=True, max_operations=100, max_payload_size=1_048_576),
   ...     filter=Filter(supported=False),
   ...     change_password=ChangePassword(supported=False),
   ...     sort=Sort(supported=False),
   ...     etag=ETag(supported=True),
   ...     authentication_schemes=[],
   ... )
   >>> app = Flask(__name__)
   >>> scim2 = SCIM2(InMemoryStorage(), ScimProvider(models=[User], config=config), app=app)

The extension answers ``413`` to a bulk request beyond either limit.

Read the results
----------------

The extension runs the operations in the order the client sent them. Each operation gets its own
``status``, and a failed one also gets an error ``response``. A failure does not stop the next
operations:

.. doctest::

   >>> def create(bulk_id, user_name):
   ...     return {
   ...         "method": "POST",
   ...         "path": "/Users",
   ...         "bulkId": bulk_id,
   ...         "data": {
   ...             "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
   ...             "userName": user_name,
   ...         },
   ...     }
   >>> client = app.test_client()
   >>> response = client.post(
   ...     "/scim/v2/Bulk",
   ...     json={
   ...         "schemas": ["urn:ietf:params:scim:api:messages:2.0:BulkRequest"],
   ...         "Operations": [create("a", "alice"), create("b", "alice"), create("c", "carol")],
   ...     },
   ...     headers={"Content-Type": "application/scim+json"},
   ... )
   >>> [(operation["bulkId"], operation["status"]) for operation in response.json["Operations"]]
   [('a', '201'), ('b', '409'), ('c', '201')]
   >>> response.json["Operations"][1]["response"]["detail"]
   "userName 'alice' is already taken"

A client that sets ``failOnErrors`` stops the request after that many failures. The operations
that already succeeded stay applied: the extension does not undo them.

Operations on existing resources, with ``PUT``, ``PATCH`` or ``DELETE``, can carry a ``version``.
When the resource has one, an operation whose ``version`` differs gets the status ``412``, as
:doc:`support-conditional-requests` describes for single requests.

The extension does not resolve ``bulkId`` references between operations.
:doc:`../explanation/limitations` explains why.
