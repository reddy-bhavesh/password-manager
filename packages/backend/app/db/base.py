from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Ensure model metadata is registered for migrations/autogenerate.
from app.models.audit_log import AuditLog  # noqa: E402,F401
from app.models.auth_session import Session  # noqa: E402,F401
from app.models.folder import Collection, CollectionMember, Folder  # noqa: E402,F401
from app.models.organization import Organization  # noqa: E402,F401
from app.models.user import User  # noqa: E402,F401
from app.models.vault_item import VaultItem, VaultItemRevision  # noqa: E402,F401
