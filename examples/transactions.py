"""Commit the changes of each SCIM request in a database session."""

from typing import Any

from flask import Blueprint
from flask import Response
from scim2_models import ScimProvider
from scim2_server.storage import ScimStorage

from scim2_flask import ScimServer


class TransactionalScimServer(ScimServer):
    def __init__(
        self, storage: ScimStorage, provider: ScimProvider, session: Any, **kwargs: Any
    ) -> None:
        self.session = session
        super().__init__(storage, provider, **kwargs)

    def create_blueprint(self) -> Blueprint:
        blueprint = super().create_blueprint()

        @blueprint.after_request
        def end_transaction(response: Response) -> Response:
            if response.status_code < 500:
                self.session.commit()
            else:
                self.session.rollback()
            return response

        return blueprint
