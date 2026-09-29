Announced features
==================

A SCIM server describes the optional features it supports at ``/ServiceProviderConfig``
(:rfc:`RFC7644 §4 <7644#section-4>`). Clients rely on that description, so it must match what the
server does. This page explains who keeps the two in line.

Why the description comes from the application
----------------------------------------------

The extension cannot tell what a storage supports. A storage may filter but not sort, or cap its
pages at a size only its backend imposes. The application describes the service in the
:class:`~scim2_models.ScimProvider`, next to the storage it wrote.

When the provider has no ``config``, the extension announces a default configuration, which
supports PATCH and no other feature. PATCH needs nothing from the storage beyond ``update``, so
every storage supports it. The other features stay off until the application announces them.

Why the extension refuses some requests only
--------------------------------------------

The extension refuses the requests that rely on filtering, PATCH or bulk operations when the
service does not announce them, but it lets sorting and ETags through.
:doc:`../how-to/announce-supported-features` lists the answers. The line follows two questions:
who implements the feature, and whether the specifications say how to answer.

Filtering, PATCH and bulk operations go through the extension. It parses the filter, applies the
PATCH operations, and runs the bulk operations one by one. It can therefore refuse them before the
storage is involved, and the specifications tell it how:

- :rfc:`RFC7644 §3.4.2.2 <7644#section-3.4.2.2>`: "Providers MUST decline to filter results if
  the specified filter operation is not recognized and return an HTTP 400 error with a
  "scimType" error of "invalidFilter"";
- :rfc:`RFC7644 §3.12 <7644#section-3.12>`, Table 8, describes ``501 (Not Implemented)`` as
  "Service provider does not support the request operation, e.g., PATCH.";
- :rfc:`RFC7644 §3.7.4 <7644#section-3.7.4>`, on the bulk limits: "If either limit is exceeded,
  the service provider MUST return HTTP response code 413 (Payload Too Large)."

Sorting and ETags depend on the storage. The storage orders the search results, and sets the
version of each resource. The specifications also leave the answer open: sorting and ETags are
OPTIONAL (:rfc:`RFC7644 §3.4.2.3 <7644#section-3.4.2.3>` and :rfc:`§3.14 <7644#section-3.14>`),
and neither section says how to answer a client that uses them anyway. The extension passes such
requests on, and the description stays accurate as long as the storage does not implement what
the service does not announce.

The size of a search page depends on the storage too, which keeps it within ``maxResults``.
