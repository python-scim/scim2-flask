What the extension leaves out
=============================

scim2-flask does not implement every part of the SCIM specifications. This page lists what it
leaves out, and why.

Authentication and authorization
--------------------------------

Every SCIM endpoint the extension serves is open. Applications authenticate their clients in many
ways: OAuth 2.0 bearer tokens, HTTP basic authentication, client certificates. They also decide
differently which client may see or change which resource. No single scheme would fit them all,
so the application adds its own, as :doc:`../how-to/protect-the-endpoints` shows.

For the same reason, the ``ServiceProviderConfig`` the extension announces by default lists no
authentication scheme. The application describes the one it implements.

The ``/Me`` endpoint
--------------------

``/Me`` designates the resource of the authenticated client. The extension does not know who the
client is, so it cannot resolve that alias, and it answers ``501``.
:rfc:`RFC7644 §3.11 <7644#section-3.11>`: "A service provider that does NOT support this feature
SHOULD respond with HTTP status code 501 (Not Implemented)."

``bulkId`` references
---------------------

In a bulk request, an operation can refer to a resource that an earlier operation of the same
request creates, with a temporary ``bulkId``. :rfc:`RFC7644 §3.7.2 <7644#section-3.7.2>`: "The
service provider MUST replace the string "bulkId:qwerty" with the permanent resource id once
created."

The extension does not replace these references. Resolving them means ordering the operations by
their dependencies, and detecting circular references, which the
:doc:`scim2-models helpers <scim2_models:integrations/helpers>` the extension draws from do not do
either. A client that needs them can send the dependent operations in separate requests.
