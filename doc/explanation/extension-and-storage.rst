The extension and the storage
=============================

scim2-flask splits a SCIM server in two. The extension speaks the protocol, and the storage keeps
the resources. This page explains where the line runs, and why.

What the extension does
-----------------------

The extension handles everything the SCIM specifications define in the same way for every server:

- the routes of every resource type, of the server root and of the discovery endpoints;
- the validation of each payload in the :class:`~scim2_models.Context` of its operation, so that
  a creation request and a replacement request accept different attributes;
- the application of PUT and PATCH requests to the stored resource;
- the ``If-Match`` and ``If-None-Match`` checks;
- the orchestration of bulk requests;
- the conversion of every failure into a SCIM error payload.

Most of this work relies on :doc:`scim2-models <scim2_models:index>`. The extension connects it to
Flask.

What the storage does
---------------------

The storage handles everything that depends on the backend: where the resources live, and how to
find them. That covers the identifiers and the dates, the uniqueness of attributes, and the
filtering, sorting and paging of searches.

Uniqueness is a good example. Only the storage sees every resource, and only a database can check
a constraint atomically against concurrent writes. The same holds for searches: a SQL storage can
translate the filter into a query, where the extension could only walk every resource.

Why ``update`` receives the whole resource
------------------------------------------

A PATCH request describes changes: add this value, remove that entry, replace the entries a
filter matches. Applying them correctly takes the SCIM path grammar, and the rules on immutable,
read-only and required attributes. scim2-models implements them, so the extension applies the
request to the stored resource, and hands the storage the result.

The storage then needs a single ``update`` method, for PUT and PATCH alike, and it only persists a
state. A storage that received the operations would have to implement the PATCH rules for its own
backend, and each implementation could get them wrong in its own way.

The price is a read before each write, and a full write where a partial one would do.

Who fills ``meta``
------------------

Every resource a SCIM server returns carries a ``meta`` attribute, which describes the resource
rather than the identity it represents (:rfc:`RFC7643 §3.1 <7643#section-3.1>`): its resource
type, its creation and modification dates, its URL and its version. None of these values comes
from the client. The server computes them all, and in scim2-flask, the extension and the storage
share that work. The storage sets ``meta.resourceType``, ``created`` and ``lastModified``, and the
extension sets ``meta.location``. Each value goes to the side that has the information it needs.

The dates belong to the storage, since only the storage knows when it wrote a resource.

``meta.resourceType`` also comes from the storage, because the model does not identify the
resource type. Two resource types may share a schema, such as users and administrators. A search
at the server root returns resources of every type in one list, and the extension reads
``meta.resourceType`` to know the endpoint of each one.

``meta.location`` depends on the routes: the URL prefix, and the host the client reached. The
extension knows them, and the storage does not. An application that needs other URLs overrides
:meth:`~scim2_flask.SCIM2.resource_location`, in one place.

``meta.version`` comes from the storage too, as :doc:`versioning` explains.
