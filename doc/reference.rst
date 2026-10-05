Reference
=========

This reference describes the public scim2-flask API.

Extension
---------

The Flask extension serving the SCIM endpoints.

.. autoclass:: scim2_flask.SCIM2
   :members:

Storage
-------

The contract a storage backend implements, and the exception it raises.

.. autoclass:: scim2_flask.ScimStorage
   :members:

.. autoclass:: scim2_flask.ResourceNotFoundError
   :members:
