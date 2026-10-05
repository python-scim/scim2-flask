Connect your own storage
========================

Use this guide when the resources live in your own backend, such as a SQL database or an LDAP
directory. The extension reads and writes them through a :class:`~scim2_flask.ScimStorage`
subclass, and handles the rest of the protocol.

The examples below come from the ``InMemoryStorage`` of the :doc:`../tutorial`, which keeps the
resources in a dictionary.

Subclass the storage
--------------------

Subclass :class:`~scim2_flask.ScimStorage`, and implement its five methods: ``query``,
``search``, ``create``, ``update`` and ``delete``. Pass an instance to the extension:

.. code-block:: python

   from scim2_flask import SCIM2, ScimStorage


   class MyStorage(ScimStorage): ...


   SCIM2(MyStorage(), provider, app=app)

Every method receives the :class:`~scim2_models.ResourceType` it applies to. Keep the resources
of each resource type apart, by the resource type ``name``: two resource types may share a
schema, as :doc:`serve-several-resource-types` shows.

Every resource a method returns must:

- be an instance of the model the provider composes for its resource type, such as
  ``User[EnterpriseUser]``. :meth:`ScimProvider.model_for <scim2_models.ScimProvider.model_for>`
  returns it;
- carry the resource type ``name`` in ``meta.resourceType``. The extension raises
  :exc:`ValueError` otherwise.

The extension sets ``meta.location`` itself.

Read a resource
---------------

``query`` returns the resource of a resource type with a given ``id``. Raise
:class:`~scim2_flask.ResourceNotFoundError` when there is none: the client receives a
``404``.

.. literalinclude:: ../../examples/minimal_server.py
   :language: python
   :pyobject: InMemoryStorage.query

Create a resource
-----------------

``create`` receives a resource the client sent, without ``id``. Give it an ``id`` and a
``meta`` holding ``resourceType``, ``created`` and ``lastModified``, store it, and return it:

.. literalinclude:: ../../examples/minimal_server.py
   :language: python
   :pyobject: InMemoryStorage.create

Raise a :class:`~scim2_models.SCIMException` to refuse the resource. The client receives the
matching SCIM error, such as ``409 uniqueness`` for a
:class:`~scim2_models.UniquenessException`.

Update a resource
-----------------

``update`` receives the complete state the resource must have, with its ``id``. The extension
already applied the PUT or PATCH request to the stored resource. Store the new state, keep
``meta.created``, update ``meta.lastModified``, and return it:

.. literalinclude:: ../../examples/minimal_server.py
   :language: python
   :pyobject: InMemoryStorage.update

Raise :class:`~scim2_flask.ResourceNotFoundError` when no resource has that ``id``.

Delete a resource
-----------------

``delete`` removes the resource of a resource type with a given ``id``. Raise
:class:`~scim2_flask.ResourceNotFoundError` when there is none:

.. literalinclude:: ../../examples/minimal_server.py
   :language: python
   :pyobject: InMemoryStorage.delete

Search resources
----------------

``search`` receives a list of resource types, and a :class:`~scim2_models.SearchRequest`. The
list holds one resource type for a search on its endpoint, such as ``/Users``, and all of them
for a search at the server root. Filter, sort and page the resources of those types as a single
collection, and return the total number of matches along with the page:

.. literalinclude:: ../../examples/minimal_server.py
   :language: python
   :pyobject: InMemoryStorage.search

The :class:`~scim2_models.SearchRequest` provides what the query needs:

- :meth:`filter.match <scim2_models.ScimFilter.match>` tells whether a resource matches the
  ``filter``;
- :meth:`~scim2_models.SearchRequest.sort` orders resources by ``sortBy`` and ``sortOrder``;
- ``start_index_0`` and ``count`` delimit the page.

Keep a page within the ``maxResults`` the provider announces, and raise a
:class:`~scim2_models.TooManyException` for a query the storage refuses to process. To translate
the filter into a database query rather than walking the resources in Python, see the
:doc:`filter transpiler <scim2_models:integrations/filter-transpiler>` of scim2-models.
