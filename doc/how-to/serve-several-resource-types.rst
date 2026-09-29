Serve several resource types
============================

Use this guide when the server exposes more than users and groups, or when two endpoints serve
resources described by the same schema, such as users and administrators.

Declare the resource types
--------------------------

Each :class:`~scim2_models.ResourceType` of the :class:`~scim2_models.ScimProvider` gets its own
endpoints. Declare a resource type for every collection, and give each one a distinct ``name``
and ``endpoint``. Here, ``/Admins`` serves resources described by the
:class:`~scim2_models.User` schema:

.. doctest::

   >>> from flask import Flask
   >>> from scim2_models import ResourceType, ScimProvider, User
   >>> from scim2_flask import SCIM2
   >>> admins = ResourceType(
   ...     id="Admin",
   ...     name="Admin",
   ...     endpoint="/Admins",
   ...     schema_="urn:ietf:params:scim:schemas:core:2.0:User",
   ... )
   >>> provider = ScimProvider(
   ...     models=[User],
   ...     resource_types=[ResourceType.from_resource(User), admins],
   ... )
   >>> app = Flask(__name__)
   >>> scim2 = SCIM2(InMemoryStorage(), provider, app=app)

To serve a resource with extensions, or a custom resource, see
:doc:`scim2-models <scim2_models:how-to/describe-a-scim-service>`.

Keep the collections apart
--------------------------

The storage receives the :class:`~scim2_models.ResourceType` of each request. Store the
resources by its ``name``, not by their schema: an administrator must not appear in ``/Users``.

.. doctest::

   >>> client = app.test_client()
   >>> response = client.post(
   ...     "/scim/v2/Admins",
   ...     json={"schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"], "userName": "root"},
   ...     headers={"Content-Type": "application/scim+json"},
   ... )
   >>> response.json["meta"]["resourceType"]
   'Admin'
   >>> client.get("/scim/v2/Users").json["totalResults"]
   0
   >>> client.get("/scim/v2/Admins").json["totalResults"]
   1

A search at the server root, ``POST /.search``, covers every resource type.
