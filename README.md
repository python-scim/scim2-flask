# scim2-flask

A [Flask](https://flask.palletsprojects.com/) extension serving a SCIM 2.0 server, as
[RFC7643](https://datatracker.ietf.org/doc/html/rfc7643) and
[RFC7644](https://datatracker.ietf.org/doc/html/rfc7644) define it. It is built upon
[scim2-server](https://scim2-server.readthedocs.io/) and
[scim2-models](https://scim2-models.readthedocs.io/). The application provides the storage.

## Features

- Resource endpoints: `POST`, `GET`, `PUT`, `PATCH` and `DELETE`, for every resource type
- Search: `GET` and `POST /.search`, per resource type and at the server root
- Discovery endpoints: `/ServiceProviderConfig`, `/ResourceTypes` and `/Schemas`
- Bulk operations: `POST /Bulk`, with `bulkId` references, `failOnErrors`, `maxOperations` and
  `maxPayloadSize`
- `/Me`, once the application tells which resource the authenticated client stands for
- Schema extensions, and several resource types sharing a schema
- Conditional requests with ETags: `If-Match` and `If-None-Match`
- SCIM error payloads for every failure

## Example

```python
from flask import Flask
from scim2_models import ScimProvider, User
from scim2_server.storage import ScimStorage

from scim2_flask import ScimServer


class MyStorage(ScimStorage):
    """Implement get, search, create, update and delete against your own storage."""

    ...


app = Flask(__name__)
ScimServer(MyStorage(), ScimProvider(models=[User]), app=app)
```

## Installation

```shell
pip install scim2-flask
```

## Documentation

- [Overview](https://scim2-flask.readthedocs.io/en/latest/overview.html) introduces the parts of
  a SCIM server built with Flask.
- [Integrate with the application](https://scim2-flask.readthedocs.io/en/latest/integrate.html)
  covers authentication, transactions, URLs and request sizes.
- [Reference](https://scim2-flask.readthedocs.io/en/latest/reference.html) lists the public API.

## What's SCIM anyway?

SCIM stands for System for Cross-domain Identity Management, and it is a provisioning protocol.
Provisioning is the action of managing a set of resources across different services, usually
users and groups. SCIM is often used between Identity Providers and applications, alongside
standards like OAuth2 and OpenID Connect. It allows users and groups creations, modifications and
deletions to be synchronized between applications.

## Getting help

Questions and bug reports go to the
[issue tracker](https://github.com/python-scim/scim2-flask/issues).

## Contributing

The [contribution page](https://scim2-flask.readthedocs.io/en/latest/contributing.html)
describes how to run the tests, the style checks and the documentation build.

## License

scim2-flask is released under the Apache-2.0 license.

scim2-flask belongs in a collection of SCIM tools developed by [Yaal Coop](https://yaal.coop),
with [scim2-models](https://github.com/python-scim/scim2-models),
[scim2-client](https://github.com/python-scim/scim2-client),
[scim2-server](https://github.com/python-scim/scim2-server),
[scim2-tester](https://github.com/python-scim/scim2-tester) and
[scim2-cli](https://github.com/python-scim/scim2-cli).
