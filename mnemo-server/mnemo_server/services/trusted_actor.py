"""Opt-in, server-configured JWT actor mapping for future membership serving.

This is not installed by the current UNINDEXED production composition. Legacy
subject-only mappings are deliberately not re-keyed or granted implicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid5

from mnemo.interfaces import PrincipalContextV1

from mnemo_server.auth import AuthError, validate_jwt

_ACTOR_NAMESPACE = UUID("40a8195a-7b23-57fa-a555-178f994d53bf")


@dataclass(frozen=True, slots=True)
class TrustedJWTActorMapper:
    issuer: str
    audience: str
    signing_secret: str
    allowed_algorithms: tuple[str, ...] = ("HS256",)

    def __post_init__(self) -> None:
        if not self.issuer.strip() or not self.audience.strip() or not self.signing_secret:
            raise ValueError("issuer, audience and signing secret are required")

    def from_token(self, token: str) -> PrincipalContextV1:
        """Only a verified, deployment-pinned issuer/subject can become an actor."""
        claims = validate_jwt(token, self.signing_secret, self.allowed_algorithms)
        subject = claims.get("sub")
        audience = claims.get("aud")
        if (
            claims.get("iss") != self.issuer
            or not isinstance(subject, str)
            or not subject.strip()
            or subject != subject.strip()
            or not isinstance(audience, str)
            or audience != self.audience
            or not isinstance(claims.get("exp"), int)
        ):
            raise AuthError("JWT identity is not trusted for notebook membership")
        return PrincipalContextV1(uuid5(_ACTOR_NAMESPACE, f"{self.issuer}\x00{subject}"), True)

    def from_server_subject(self, subject: str) -> PrincipalContextV1:
        """Map an explicit server-owned local transport subject, never client input."""
        if not isinstance(subject, str) or not subject or subject != subject.strip():
            raise AuthError("trusted local transport subject is unavailable")
        return PrincipalContextV1(uuid5(_ACTOR_NAMESPACE, f"{self.issuer}\x00{subject}"), True)
