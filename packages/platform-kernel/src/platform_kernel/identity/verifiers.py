"""TokenVerifier port and providers (P36). Demo tokens are refused in production (F23)."""
from __future__ import annotations

from typing import Any, Protocol

import jwt

from ..context import Principal
from ..core import DomainError, Err, Ok, Result


class TokenVerifier(Protocol):
    simulated: bool

    def verify(self, token: str) -> Result[Principal, DomainError]: ...


class JwtTokenVerifier:
    """Verifies signed JWTs with configured keys. Key discovery (JWKS) is a later provider."""

    simulated = False

    def __init__(self, key: Any, *, algorithms: list[str], audience: str, issuer: str,
                 roles_claim: str = "roles", tenant_claim: str = "tenant", leeway_seconds: int = 30,
                 platform_roles: frozenset[str] = frozenset()) -> None:
        self._key, self._alg, self._aud, self._iss = key, algorithms, audience, issuer
        self._roles, self._tenant, self._leeway = roles_claim, tenant_claim, leeway_seconds
        self._platform_roles = frozenset(platform_roles)

    def verify(self, token: str) -> Result[Principal, DomainError]:
        try:
            claims = jwt.decode(token, self._key, algorithms=self._alg, audience=self._aud, issuer=self._iss,
                                leeway=self._leeway, options={"require": ["exp", "sub", "iss", "aud"]})
        except jwt.ExpiredSignatureError:
            return Err(DomainError("TOKEN_EXPIRED", "The access token has expired."))
        except jwt.PyJWTError as exc:
            return Err(DomainError("TOKEN_INVALID", f"The access token is not valid: {exc}."))
        roles = claims.get(self._roles) or []
        role_set = frozenset(roles if isinstance(roles, list) else [roles])
        if not claims.get(self._tenant) and not (role_set & self._platform_roles):
            return Err(DomainError("TOKEN_INVALID", "The token has no tenant claim and no platform role."))
        return Ok(Principal(
            subject=str(claims["sub"]),
            roles=role_set,
            tenant=claims.get(self._tenant) or None,
            kind=claims.get("kind", "user"),
            on_behalf_of=claims.get("act", {}).get("sub") if isinstance(claims.get("act"), dict) else None,
            claims=claims,
        ))


class DemoTokenVerifier:
    """Development only. A token 'demo:<subject>:<role,role>[:<tenant>]' becomes a principal. Labeled simulated."""

    simulated = True

    def verify(self, token: str) -> Result[Principal, DomainError]:
        parts = token.split(":")
        if len(parts) < 3 or parts[0] != "demo":
            return Err(DomainError("TOKEN_INVALID", "Demo tokens look like 'demo:<subject>:<roles>[:<tenant>]'."))
        roles = frozenset(r for r in parts[2].split(",") if r)
        tenant = parts[3] if len(parts) > 3 and parts[3] else None
        return Ok(Principal(subject=parts[1], roles=roles, tenant=tenant))
