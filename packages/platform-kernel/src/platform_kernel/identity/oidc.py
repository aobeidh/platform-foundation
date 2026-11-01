"""OIDC access-token verification with keys from a JWKS source (P36). Only asymmetric algorithms are accepted."""
from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from typing import Any, Protocol

import jwt

from ..context import Principal
from ..core import DomainError, Err, Ok, Result

ALLOWED_ALGORITHMS = frozenset({"RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512",
                                "EdDSA"})


class JwksSource(Protocol):
    def keys(self, force: bool = False) -> dict[str, Any]:
        """Map of key id to public key. `force` asks for a refresh (rate limited by the provider)."""
        ...


class StaticJwksSource:
    """Keys given directly, for tests and air-gapped deployments that ship the issuer's keys."""

    def __init__(self, jwks: dict[str, Any]) -> None:
        self._keys = _parse_jwks(jwks)

    def keys(self, force: bool = False) -> dict[str, Any]:
        return self._keys


class JwksUnavailable(Exception):
    """No usable signing keys: the identity provider could not be reached and there are no last-known keys."""


def _parse_jwks(jwks: Any) -> dict[str, Any]:
    if not isinstance(jwks, dict) or not isinstance(jwks.get("keys"), list):
        raise ValueError("the JWKS document has no 'keys' list")
    out = {}
    for k in jwks["keys"]:
        if k.get("use", "sig") != "sig" or "kid" not in k:
            continue
        out[k["kid"]] = jwt.PyJWK.from_json(json.dumps(k)).key
    return out


class CachedJwksSource:
    """Wraps a fetch function with a cache and a minimum interval between refreshes, so unknown key ids cannot be
    used to hammer the identity provider. When a refresh fails (outage, error body, no usable keys) the last good
    keys stay in use and the next attempt waits for the minimum interval."""

    def __init__(self, fetch: Callable[[], dict[str, Any]], ttl_seconds: float = 300, min_refresh_seconds: float = 30,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._fetch, self._ttl, self._min = fetch, ttl_seconds, min_refresh_seconds
        self._clock, self._lock = clock, threading.Lock()
        self._keys: dict[str, Any] = {}
        self._fetched_at: float | None = None
        self._attempted_at: float | None = None

    def keys(self, force: bool = False) -> dict[str, Any]:
        with self._lock:
            now = self._clock()
            stale = self._fetched_at is None or now - self._fetched_at > self._ttl
            may_try = self._attempted_at is None or now - self._attempted_at > self._min
            if (stale or force) and may_try:
                self._attempted_at = now
                try:
                    keys = _parse_jwks(self._fetch())
                    if not keys:
                        raise ValueError("the JWKS document has no usable signing keys")
                    self._keys, self._fetched_at = keys, now
                except Exception:  # noqa: BLE001 - keep the last good keys; back off before retrying
                    pass
            if not self._keys:
                raise JwksUnavailable("no signing keys are available")
            return self._keys


class OidcTokenVerifier:
    simulated = False

    def __init__(self, keys: JwksSource, *, issuer: str, audience: str, algorithms: tuple[str, ...] = ("RS256",),
                 roles_claim: str = "roles", tenant_claim: str = "tenant", leeway_seconds: int = 30,
                 platform_roles: frozenset[str] = frozenset()) -> None:
        """`platform_roles`: roles that make a token without a tenant claim a platform (staff) token. Any other token
        without a tenant claim is refused, so a missing claim never widens access (P22)."""
        bad = set(algorithms) - ALLOWED_ALGORITHMS
        if bad:
            raise ValueError(f"algorithms {sorted(bad)} are not allowed; use asymmetric algorithms only")
        self._keys, self._iss, self._aud, self._alg = keys, issuer, audience, list(algorithms)
        self._roles, self._tenant, self._leeway = roles_claim, tenant_claim, leeway_seconds
        self._platform_roles = frozenset(platform_roles)

    def verify(self, token: str) -> Result[Principal, DomainError]:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            return Err(DomainError("TOKEN_INVALID", f"The access token is not a JWT: {exc}."))
        if header.get("alg") not in self._alg:
            return Err(DomainError("TOKEN_INVALID", f"Token algorithm {header.get('alg')!r} is not accepted."))
        kid = header.get("kid")
        try:
            key = self._keys.keys().get(kid) if kid else None
            if key is None and kid:
                key = self._keys.keys(force=True).get(kid)  # key rotation: refresh once, rate limited
        except JwksUnavailable:
            return Err(DomainError("DEPENDENCY_UNAVAILABLE", "Tokens cannot be verified right now; try again."))
        if key is None:
            return Err(DomainError("TOKEN_INVALID", "The token is signed with an unknown key."))
        try:
            claims = jwt.decode(token, key, algorithms=self._alg, audience=self._aud, issuer=self._iss,
                                leeway=self._leeway, options={"require": ["exp", "iat", "sub", "iss", "aud"]})
        except jwt.ExpiredSignatureError:
            return Err(DomainError("TOKEN_EXPIRED", "The access token has expired."))
        except jwt.PyJWTError as exc:
            return Err(DomainError("TOKEN_INVALID", f"The access token is not valid: {exc}."))
        roles = claims.get(self._roles) or []
        if isinstance(claims.get("realm_access"), dict) and not roles:
            roles = claims["realm_access"].get("roles", [])  # Keycloak's default placement
        act = claims.get("act")
        role_set = frozenset(roles if isinstance(roles, list) else [roles])
        tenant = claims.get(self._tenant)
        if not tenant and not (role_set & self._platform_roles):
            return Err(DomainError("TOKEN_INVALID", "The token has no tenant claim and no platform role."))
        return Ok(Principal(
            subject=str(claims["sub"]),
            roles=role_set,
            tenant=tenant or None,
            kind=str(claims.get("kind", "service" if claims.get("client_id") == claims["sub"] else "user")),
            on_behalf_of=str(act["sub"]) if isinstance(act, dict) and "sub" in act else None,
            claims=claims,
        ))


class TokenExchanger(Protocol):
    """RFC 8693: exchange the caller's token for one aimed at another service, keeping the user as subject."""

    def exchange(self, subject_token: str, audience: str) -> str: ...


class ServiceTokens(Protocol):
    """Client-credentials tokens for calls the service makes as itself (reference data, jobs)."""

    def token(self, audience: str) -> str: ...
