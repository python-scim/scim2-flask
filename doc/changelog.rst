Changelog
=========

[0.1.1] - 2026-10-10
--------------------

Added
^^^^^
- Cursor pagination (:rfc:`RFC 9865 <9865>`). The cursors are encrypted with the
  :data:`~flask:SECRET_KEY` of the application.

Changed
^^^^^^^
- Requires scim2-server 0.8.0 and scim2-models 0.12.2.
- :meth:`~scim2_flask.ScimServer.init_app` builds the service, rather than the constructor.

[0.1.0] - 2026-10-06
--------------------

Added
^^^^^
- :class:`~scim2_flask.ScimServer`, a Flask extension serving the endpoints of :rfc:`RFC 7644 <7644>`
  over a :class:`~scim2_server.storage.ScimStorage`. The SCIM protocol is handled by
  :doc:`scim2-server <scim2_server:index>`.
