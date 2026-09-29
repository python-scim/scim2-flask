Check the server conformance
============================

Use this guide to check that your server follows :rfc:`RFC 7643 <7643>` and
:rfc:`RFC 7644 <7644>`, your storage included, for instance in your test suite. The scim2-flask
test suite checks the extension with the in-memory storage of the :doc:`../tutorial` only, while
much of the conformance depends on the storage, as :doc:`connect-a-storage` shows.

:doc:`scim2-tester <scim2_tester:index>` sends the server the requests a SCIM client would, and
reports the answers that break the specifications.

Install scim2-tester:

.. code-block:: shell

   pip install scim2-tester

Run the checks
--------------

Wrap the application in a scim2-client test client, and pass it to
:func:`~scim2_tester.check_server`:

.. doctest::

   >>> from flask import Flask
   >>> from scim2_client.engines.werkzeug import TestSCIMClient
   >>> from scim2_tester import check_server
   >>> from werkzeug.test import Client
   >>> from scim2_flask import SCIM2
   >>> app = Flask(__name__)
   >>> scim2 = SCIM2(InMemoryStorage(), create_provider(), app=app)
   >>> client = TestSCIMClient(Client(app), scim_prefix="/scim/v2", provider=scim2.provider)
   >>> results = check_server(client, include_tags={"discovery", "crud:create"})
   >>> sorted({result.status.name for result in results})
   ['SKIPPED', 'SUCCESS']

The server conforms when every check succeeds, or is skipped because the server does not
announce the feature it checks. Each result also has a ``title`` naming the check, and a
``reason`` when it fails. Leave ``include_tags`` out to run every check.
