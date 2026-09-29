Tutorial
========

In this tutorial, we will build a SCIM server that stores users and groups in memory. We will
then create and read resources with ``curl``, as a SCIM client would.

We need Python 3.11 or later, and ``curl``.

Install scim2-flask
-------------------

First, install scim2-flask. It brings Flask and scim2-models along:

.. code-block:: shell

   pip install scim2-flask

Now create an empty file named ``server.py``. We will fill it step by step.

Import the building blocks
--------------------------

Start ``server.py`` with the imports, and with the limits the server will announce to its
clients:

.. literalinclude:: ../examples/minimal_server.py
   :language: python
   :start-at: import hashlib
   :end-before: def make_etag

Describe the service
--------------------

A :class:`~scim2_models.ScimProvider` describes what the server serves. Ours serves users, with
the enterprise extension, and groups. It also lists the features the server supports, such as
filtering and sorting:

.. literalinclude:: ../examples/minimal_server.py
   :language: python
   :pyobject: create_provider

Store the resources
-------------------

The extension handles the SCIM protocol, but it does not store anything. A
:class:`~scim2_flask.ScimStorage` subclass does.

Our storage gives each resource a version when it creates or updates it. Clients use that version
to detect concurrent changes. Add the function computing it:

.. literalinclude:: ../examples/minimal_server.py
   :language: python
   :pyobject: make_etag

Then add the storage class. It keeps the resources in a dictionary, one per resource type:

.. literalinclude:: ../examples/minimal_server.py
   :language: python
   :pyobject: InMemoryStorage
   :end-before:     def search(

Add a ``search`` method to the class. It filters, sorts and pages the resources, as the client
asks:

.. literalinclude:: ../examples/minimal_server.py
   :language: python
   :pyobject: InMemoryStorage.search

Add the ``create`` and ``update`` methods to the class. They also check that no two users
share a ``userName``:

.. literalinclude:: ../examples/minimal_server.py
   :language: python
   :pyobject: InMemoryStorage.create

.. literalinclude:: ../examples/minimal_server.py
   :language: python
   :pyobject: InMemoryStorage.update

.. literalinclude:: ../examples/minimal_server.py
   :language: python
   :pyobject: InMemoryStorage._check_user_name_unique

Finally, add the ``delete`` method:

.. literalinclude:: ../examples/minimal_server.py
   :language: python
   :pyobject: InMemoryStorage.delete

Create the application
----------------------

The :class:`~scim2_flask.SCIM2` extension connects the storage and the provider to a Flask
application. Add the application factory, and the lines starting the server:

.. literalinclude:: ../examples/minimal_server.py
   :language: python
   :pyobject: create_app

.. literalinclude:: ../examples/minimal_server.py
   :language: python
   :start-at: if __name__ == "__main__":

Start the server:

.. code-block:: shell

   python server.py

The output should look something like this:

.. code-block:: text

    * Serving Flask app 'server'
    * Debug mode: on
    * Running on http://127.0.0.1:5000

Leave the server running, and open a second terminal for the next steps.

Create a user
-------------

Send a user to the ``/Users`` endpoint:

.. code-block:: shell

   curl -X POST http://localhost:5000/scim/v2/Users \
       -H "Content-Type: application/scim+json" \
       -d '{"schemas": ["urn:ietf:params:scim:schemas:core:2.0:User",
                        "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"],
            "userName": "bjensen",
            "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User": {"employeeNumber": "42"}}'

The server answers with the user it stored:

.. code-block:: json

   {
     "id": "fc4cd4d3-3667-4872-9d98-11ca9ad19303",
     "meta": {
       "created": "2026-09-29T12:53:13.116241Z",
       "lastModified": "2026-09-29T12:53:13.116241Z",
       "location": "http://localhost:5000/scim/v2/Users/fc4cd4d3-3667-4872-9d98-11ca9ad19303",
       "resourceType": "User",
       "version": "W/\"a7142e634095740c\""
     },
     "schemas": [
       "urn:ietf:params:scim:schemas:core:2.0:User",
       "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"
     ],
     "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User": {
       "employeeNumber": "42"
     },
     "userName": "bjensen"
   }

Notice that the user now has an ``id`` and a ``meta`` attribute. The storage set the ``id`` and
the dates, and the extension added the ``location``. Your ``id``, dates and ``version`` differ
from the ones above.

Read the user back
------------------

Copy the ``location`` from the output, and request it:

.. code-block:: shell

   curl http://localhost:5000/scim/v2/Users/fc4cd4d3-3667-4872-9d98-11ca9ad19303

The server answers with the same user:

.. code-block:: json

   {
     "id": "fc4cd4d3-3667-4872-9d98-11ca9ad19303",
     "meta": {
       "created": "2026-09-29T12:53:13.116241Z",
       "lastModified": "2026-09-29T12:53:13.116241Z",
       "location": "http://localhost:5000/scim/v2/Users/fc4cd4d3-3667-4872-9d98-11ca9ad19303",
       "resourceType": "User",
       "version": "W/\"a7142e634095740c\""
     },
     "schemas": [
       "urn:ietf:params:scim:schemas:core:2.0:User",
       "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"
     ],
     "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User": {
       "employeeNumber": "42"
     },
     "userName": "bjensen"
   }

Create the user again
---------------------

Send the same user a second time:

.. code-block:: shell

   curl -X POST http://localhost:5000/scim/v2/Users \
       -H "Content-Type: application/scim+json" \
       -d '{"schemas": ["urn:ietf:params:scim:schemas:core:2.0:User",
                        "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"],
            "userName": "bjensen",
            "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User": {"employeeNumber": "42"}}'

The storage refuses it, since another user already has this ``userName``:

.. code-block:: json

   {
     "detail": "userName 'bjensen' is already taken",
     "schemas": [
       "urn:ietf:params:scim:api:messages:2.0:Error"
     ],
     "scimType": "uniqueness",
     "status": "409"
   }

Create a group
--------------

Send a group to the ``/Groups`` endpoint:

.. code-block:: shell

   curl -X POST http://localhost:5000/scim/v2/Groups \
       -H "Content-Type: application/scim+json" \
       -d '{"schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"], "displayName": "Engineers"}'

The server answers with the group it stored:

.. code-block:: json

   {
     "displayName": "Engineers",
     "id": "5914328f-2ec1-4ddf-89a0-37a1fdba328f",
     "meta": {
       "created": "2026-09-29T12:53:13.129902Z",
       "lastModified": "2026-09-29T12:53:13.129902Z",
       "location": "http://localhost:5000/scim/v2/Groups/5914328f-2ec1-4ddf-89a0-37a1fdba328f",
       "resourceType": "Group",
       "version": "W/\"826f4129f68ddc27\""
     },
     "schemas": [
       "urn:ietf:params:scim:schemas:core:2.0:Group"
     ]
   }

List the groups
---------------

Request the ``/Groups`` endpoint:

.. code-block:: shell

   curl http://localhost:5000/scim/v2/Groups

The server answers with a list holding the group we created:

.. code-block:: json

   {
     "Resources": [
       {
         "displayName": "Engineers",
         "id": "5914328f-2ec1-4ddf-89a0-37a1fdba328f",
         "meta": {
           "created": "2026-09-29T12:53:13.129902Z",
           "lastModified": "2026-09-29T12:53:13.129902Z",
           "location": "http://localhost:5000/scim/v2/Groups/5914328f-2ec1-4ddf-89a0-37a1fdba328f",
           "resourceType": "Group",
           "version": "W/\"826f4129f68ddc27\""
         },
         "schemas": [
           "urn:ietf:params:scim:schemas:core:2.0:Group"
         ]
       }
     ],
     "itemsPerPage": 1,
     "schemas": [
       "urn:ietf:params:scim:api:messages:2.0:ListResponse"
     ],
     "startIndex": 1,
     "totalResults": 1
   }

Notice that ``/Groups`` lists only the group: each resource type has its own collection.

What we built
-------------

We built a SCIM server that creates, reads and lists users and groups. The same server also
answers PUT, PATCH, DELETE, search and bulk requests, and describes itself at
``/ServiceProviderConfig``, ``/ResourceTypes`` and ``/Schemas``.

The complete ``server.py`` is available as
`examples/minimal_server.py <https://github.com/python-scim/scim2-flask/blob/main/examples/minimal_server.py>`_.
The :doc:`reference` describes :class:`~scim2_flask.SCIM2` and
:class:`~scim2_flask.ScimStorage` in full.
