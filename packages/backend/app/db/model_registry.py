"""Import all models so SQLAlchemy metadata is fully populated."""

from app.models.audit_log import AuditLog  # noqa: F401
from app.models.auth_session import Session  # noqa: F401
from app.models.folder import Collection, CollectionItem, CollectionMember, Folder  # noqa: F401
from app.models.group import Group, GroupMember  # noqa: F401
from app.models.mfa_totp_credential import MfaTotpCredential  # noqa: F401
from app.models.organization import Organization  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.vault_item import VaultItem, VaultItemRevision  # noqa: F401
