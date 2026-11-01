"""OAuth 2.0 token service: client credentials (the service as itself) and RFC 8693 token exchange (acting for the
caller). Both go through the resilient, egress-bound client (P23, P26, P36). Tokens are cached until shortly before
they expire; the cache key never stores the subject token itself."""
from __future__ import annotations

import hashlib
import threading
import time
from collections.abc import Callable
from typing import Any

from ..core import DomainError
from .client import OutboundError, ResilientClient

EXCHANGE_GRANT = "urn:ietf:params:oauth:grant-type:token-exchange"
ACCESS_TOKEN = "urn:ietf:params:oauth:token-type:access_token"


class OAuthTokenService:
    simulated = False
    MAX_ENTRIES = 10_000

    def __init__(self, client: ResilientClient, token_path: str, client_id: str, client_secret: Callable[[], str],
                 *, early_refresh_seconds: float = 30, clock: Callable[[], float] = time.time) -> None:
        self._client, self._path = client, token_path
        self._id, self._secret = client_id, client_secret
        self._early, self._clock = early_refresh_seconds, clock
        self._cache: dict[str, tuple[str, float]] = {}
        self._lock = threading.Lock()

    def _cached(self, key: str) -> str | None:
        with self._lock:
            hit = self._cache.get(key)
            if hit and hit[1] - self._early > self._clock():
                return hit[0]
            return None

    def _request(self, key: str, form: dict[str, str]) -> str:
        cached = self._cached(key)
        if cached:
            return cached
        response = self._client.request("POST", self._path, data=form, auth=(self._id, self._secret()))
        if response.status_code != 200:
            raise OutboundError(DomainError("DEPENDENCY_UNAVAILABLE",
                                            f"The token service refused the request ({response.status_code})."))
        body: dict[str, Any] = response.json()
        token = body.get("access_token")
        if not token:
            raise OutboundError(DomainError("DEPENDENCY_UNAVAILABLE", "The token service returned no access token."))
        expires = self._clock() + float(body.get("expires_in", 60))
        with self._lock:
            self._cache.pop(key, None)
            self._cache[key] = (token, expires)  # newest last: dicts keep insertion order
            while len(self._cache) > self.MAX_ENTRIES:
                self._cache.pop(next(iter(self._cache)))  # hard bound: evict the oldest entry
        return token

    def token(self, audience: str) -> str:
        return self._request(f"cc\n{audience}", {"grant_type": "client_credentials", "audience": audience})

    def exchange(self, subject_token: str, audience: str) -> str:
        digest = hashlib.sha256(subject_token.encode()).hexdigest()
        return self._request(f"x\n{audience}\n{digest}", {
            "grant_type": EXCHANGE_GRANT, "subject_token": subject_token, "subject_token_type": ACCESS_TOKEN,
            "requested_token_type": ACCESS_TOKEN, "audience": audience})
