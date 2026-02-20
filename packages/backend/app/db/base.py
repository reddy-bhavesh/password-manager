from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Ensure model metadata is registered for migrations/autogenerate.
from app.models.organization import Organization  # noqa: E402,F401
from app.models.user import User  # noqa: E402,F401
from app.models.vault_item import VaultItem, VaultItemRevision  # noqa: E402,F401
