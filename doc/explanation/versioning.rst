Resource versions
=================

Two clients that modify the same resource at the same time may overwrite each other's changes.
SCIM prevents it with ETags (:rfc:`RFC7644 §3.14 <7644#section-3.14>`): each resource carries a
version, and a client makes its modification conditional on the version it read.

Who does what
-------------

The storage computes the versions, and the extension compares them.

A version must change whenever the resource changes, and only the storage writes resources. It
sets ``meta.version`` on each resource it creates or updates.

The extension does the rest, the same way for every storage:

- it sends the version in the ``ETag`` header;
- it answers ``304 Not Modified`` to a ``GET`` whose ``If-None-Match`` holds the current version;
- it answers ``412 Precondition Failed`` to a ``PUT``, ``PATCH`` or ``DELETE`` whose ``If-Match``
  holds another version;
- it compares the ``version`` of each bulk operation in the same way.

A resource without version skips these checks. A storage without versioning therefore works
unchanged, and its clients simply cannot make their requests conditional.

Why the example uses weak ETags
-------------------------------

A strong ETag promises that two representations are identical byte for byte. A weak ETag only
promises that they are equivalent. :rfc:`RFC7644 §3.14 <7644#section-3.14>`: "Service providers
MAY support weak ETags as the preferred mechanism for performing conditional retrievals and
ensuring that clients do not inadvertently overwrite each other's changes, respectively."

A SCIM server returns several representations of the same resource, depending on the
``attributes`` a client asks for, so a byte-for-byte promise would not hold. The example storage
hashes the content of the resource instead, with its dates, as the
:doc:`scim2-models helpers <scim2_models:integrations/helpers>` do. Every write therefore yields a
new version, even one that changes nothing else.

A database storage may use a counter it increments on each write, or a timestamp. Any value works,
as long as it changes with the resource.
