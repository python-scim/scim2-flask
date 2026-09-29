Tolerate a nonconformant client
===============================

Use this guide when a real SCIM client sends payloads the server refuses, such as attributes no
schema declares. The extension reads every payload under the :class:`~scim2_models.ScimPolicy` of
the :class:`~scim2_models.ScimProvider`, and the policy says how much to accept beyond what
:rfc:`RFC7643 <7643>` and :rfc:`RFC7644 <7644>` describe.

Set the policy
--------------

By default, the server refuses a payload carrying an unknown attribute:

.. doctest::

   >>> from flask import Flask
   >>> from scim2_models import ScimPolicy, ScimProvider, User
   >>> from scim2_flask import SCIM2
   >>> payload = {
   ...     "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
   ...     "userName": "bjensen",
   ...     "vendorAttribute": "some value",
   ... }
   >>> headers = {"Content-Type": "application/scim+json"}
   >>> app = Flask(__name__)
   >>> scim2 = SCIM2(InMemoryStorage(), ScimProvider(models=[User]), app=app)
   >>> app.test_client().post("/scim/v2/Users", json=payload, headers=headers).status_code
   400

Give the provider a policy that ignores unknown attributes. The server then stores the rest of the
payload:

.. doctest::

   >>> policy = ScimPolicy(unknown=ScimPolicy.Unknown.ignore)
   >>> app = Flask(__name__)
   >>> scim2 = SCIM2(InMemoryStorage(), ScimProvider(models=[User], policy=policy), app=app)
   >>> response = app.test_client().post("/scim/v2/Users", json=payload, headers=headers)
   >>> response.status_code
   201
   >>> "vendorAttribute" in response.json
   False

The policy applies to every request the extension serves, bulk operations included.

Choose the settings
-------------------

A :class:`~scim2_models.ScimPolicy` has other settings, for the PATCH requests some clients send.
Each one defaults to the strict reading of the specifications. The scim2-models guide
:doc:`scim2_models:how-to/tolerate-a-nonconformant-peer` describes them, and the clients they
help.
