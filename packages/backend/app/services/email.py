from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.core.settings import settings


class InvitationEmailSender(Protocol):
    async def send_invitation(
        self,
        *,
        recipient_email: str,
        invitation_link: str,
    ) -> None: ...


@dataclass
class StubInvitationEmailSender:
    enabled: bool = settings.invitation_email_enabled

    async def send_invitation(
        self,
        *,
        recipient_email: str,
        invitation_link: str,
    ) -> None:
        if not self.enabled:
            return
        _ = (recipient_email, invitation_link)
