Announce the supported features
===============================

Use this guide to tell clients which optional SCIM features the server supports, such as
filtering or bulk operations. Clients read them at ``/ServiceProviderConfig``
(:rfc:`RFC7644 §4 <7644#section-4>`).

Describe the features
---------------------

Give the :class:`~scim2_models.ScimProvider` a :class:`~scim2_models.ServiceProviderConfig`.
Announce only what the storage actually does:

.. doctest::

   >>> from flask import Flask
   >>> from scim2_models import (
   ...     Bulk, ChangePassword, ETag, Filter, Patch, ScimProvider, ServiceProviderConfig,
   ...     Sort, User,
   ... )
   >>> from scim2_flask import SCIM2
   >>> config = ServiceProviderConfig(
   ...     patch=Patch(supported=True),
   ...     bulk=Bulk(supported=False, max_operations=0, max_payload_size=0),
   ...     filter=Filter(supported=True, max_results=50),
   ...     change_password=ChangePassword(supported=False),
   ...     sort=Sort(supported=True),
   ...     etag=ETag(supported=True),
   ...     authentication_schemes=[],
   ... )
   >>> app = Flask(__name__)
   >>> scim2 = SCIM2(InMemoryStorage(), ScimProvider(models=[User], config=config), app=app)

Give every attribute, even for the features the server does not support: the extension announces
the configuration as it is. :rfc:`RFC7643 §5 <7643#section-5>` requires all of them, and
recommends ``authenticationSchemes``.

When the provider has no ``config``, the extension announces a default configuration instead: it
supports PATCH, and no other feature.

Know what the extension enforces
--------------------------------

The extension refuses the requests that go beyond what the service announces:

- a ``filter`` answers ``400 invalidFilter``, when ``filter`` is not supported;
- a ``PATCH``, or a PATCH operation in a bulk request, answers ``501``, when ``patch`` is not
  supported;
- a ``POST /Bulk`` answers ``501``, when ``bulk`` is not supported;
- a bulk request beyond ``maxOperations`` or ``maxPayloadSize`` answers ``413``.

.. doctest::

   >>> client = app.test_client()
   >>> response = client.post("/scim/v2/Bulk", json={}, headers={"Content-Type": "application/scim+json"})
   >>> response.status_code
   501

It passes the other requests to the storage, even when they rely on a feature announced as
unsupported:

- without ``sort``, the storage still receives ``sortBy`` and ``sortOrder``. Leave them unused;
- without ``etag``, the extension still sends the ``meta.version`` the storage sets, and checks
  ``If-Match`` and ``If-None-Match`` against it. Leave ``meta.version`` unset.

The storage also enforces ``maxResults``: keep every search page within it, as
:doc:`connect-a-storage` describes.

:doc:`../explanation/announced-features` explains why the extension refuses some requests only.
