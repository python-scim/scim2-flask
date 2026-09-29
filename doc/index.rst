scim2-flask
===========

scim2-flask is a `Flask <https://flask.palletsprojects.com/en/stable/>`_ extension serving a SCIM
2.0 server, as :rfc:`RFC 7643 <7643>` and :rfc:`RFC 7644 <7644>` define it. It exposes the
resource, search, bulk and discovery endpoints, and relies on
:doc:`scim2-models <scim2_models:index>` to validate and serialize the payloads.

An application gives the extension a storage, here the ``InMemoryStorage`` of the
:doc:`tutorial`, and the models it serves. Clients can then create users:

.. doctest::

   >>> from flask import Flask
   >>> from scim2_models import ScimProvider, User
   >>> from scim2_flask import SCIM2
   >>> app = Flask(__name__)
   >>> scim2 = SCIM2(InMemoryStorage(), ScimProvider(models=[User]), app=app)
   >>> response = app.test_client().post(
   ...     "/scim/v2/Users",
   ...     json={"schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"], "userName": "bjensen"},
   ... )
   >>> response.status_code
   201
   >>> response.json["userName"]
   'bjensen'

The extension handles the SCIM protocol. The application must provide the rest:

- a :class:`~scim2_flask.ScimStorage` subclass, which reads and writes the resources;
- a :class:`~scim2_models.ScimProvider`, which declares the resource types the server serves and
  the features it supports;
- authentication and authorization, since the extension leaves every endpoint open.

This documentation addresses Python developers who build a SCIM server with Flask. It assumes
familiarity with Flask applications, and with the models of :doc:`scim2-models <scim2_models:overview>`.

.. code-block:: shell

   pip install scim2-flask

Choose a path
-------------

:doc:`Tutorial <tutorial>` builds a first SCIM server, step by step.

:doc:`How-to guides <how-to/index>` show how to complete a specific task, such as connecting your
own storage.

:doc:`Explanation <explanation/index>` gives the reasons behind the behaviour of the extension,
and what it leaves out.

:doc:`Reference <reference>` lists the complete public API.

.. toctree::
    :maxdepth: 2
    :hidden:

    Tutorial <tutorial>
    How-to guides <how-to/index>
    Explanation <explanation/index>
    Reference <reference>
    Contributing <contributing>
    Changelog <changelog>
