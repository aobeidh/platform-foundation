from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import APIRouter
from fastapi.testclient import TestClient
from platform_kernel import context as ctxmod
from platform_kernel.config import MemorySecretStore, PlatformSettings
from platform_kernel.http import EgressPolicy, OAuthTokenService, ResilientClient
from platform_kernel.identity import CachedJwksSource, OidcTokenVerifier, StaticJwksSource
from platform_kernel.platform import Platform

ISS, AUD = "https://idp.example.com/realms/sdd", "connections"


def keypair(kid: str):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True) | {"kid": kid, "use": "sig"}
    return key, jwk


KEY1, JWK1 = keypair("k1")
KEY2, JWK2 = keypair("k2")


def token(key=KEY1, kid="k1", **claims) -> str:
    now = int(time.time())
    body = {"iss": ISS, "aud": AUD, "sub": "ada", "iat": now, "exp": now + 300, "roles": ["admin"],
            "tenant": "t1"} | claims
    return jwt.encode(body, key, algorithm="RS256", headers={"kid": kid})


def verifier(keys) -> OidcTokenVerifier:
    return OidcTokenVerifier(keys, issuer=ISS, audience=AUD)


def test_valid_token_becomes_a_principal():
    p = verifier(StaticJwksSource({"keys": [JWK1]})).verify(token()).value
    assert (p.subject, p.tenant, p.roles) == ("ada", "t1", frozenset({"admin"}))


def test_keycloak_realm_roles_and_actor_claim():
    p = verifier(StaticJwksSource({"keys": [JWK1]})).verify(
        token(roles=None, realm_access={"roles": ["auditor"]}, act={"sub": "hub-service"})).value
    assert p.roles == frozenset({"auditor"}) and p.on_behalf_of == "hub-service"


@pytest.mark.parametrize("bad,code", [
    (lambda: token(exp=int(time.time()) - 120), "TOKEN_EXPIRED"),
    (lambda: token(aud="other"), "TOKEN_INVALID"),
    (lambda: token(iss="https://evil"), "TOKEN_INVALID"),
    (lambda: token(key=KEY2, kid="k1"), "TOKEN_INVALID"),
    (lambda: jwt.encode({"sub": "x"}, "secret", algorithm="HS256", headers={"kid": "k1"}), "TOKEN_INVALID"),
    (lambda: "not-a-jwt", "TOKEN_INVALID"),
])
def test_bad_tokens_are_refused(bad, code):
    assert verifier(StaticJwksSource({"keys": [JWK1]})).verify(bad()).error.code == code


def test_symmetric_algorithms_cannot_be_configured():
    with pytest.raises(ValueError):
        OidcTokenVerifier(StaticJwksSource({"keys": []}), issuer=ISS, audience=AUD, algorithms=("HS256",))


def test_key_rotation_refreshes_once_and_is_rate_limited():
    fetches = []
    current = {"keys": [JWK1]}
    now = [0.0]

    def fetch():
        fetches.append(1)
        return current

    v = verifier(CachedJwksSource(fetch, ttl_seconds=300, min_refresh_seconds=30, clock=lambda: now[0]))
    assert v.verify(token()).ok and len(fetches) == 1
    current = {"keys": [JWK1, JWK2]}
    assert not v.verify(token(KEY2, "k2")).ok  # within the minimum interval: no refresh, refused
    assert len(fetches) == 1
    now[0] = 31
    assert v.verify(token(KEY2, "k2")).ok and len(fetches) == 2
    assert not v.verify(token(KEY2, "unknown")).ok and len(fetches) == 2


def _token_service(handler) -> OAuthTokenService:
    client = ResilientClient("oauth", "https://idp.example.com", transport=httpx.MockTransport(handler),
                             egress=EgressPolicy(allowlist=("idp.example.com",), resolver=lambda h: ["93.184.216.34"]))
    return OAuthTokenService(client, "/token", "hub", lambda: "s3cret")


def test_client_credentials_are_cached_until_near_expiry():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(dict(httpx.QueryParams(request.content.decode())))
        return httpx.Response(200, json={"access_token": f"t{len(calls)}", "expires_in": 300})

    svc = _token_service(handler)
    assert svc.token("catalogue") == svc.token("catalogue") == "t1"
    assert calls[0]["grant_type"] == "client_credentials" and calls[0]["audience"] == "catalogue"


def test_token_exchange_sends_rfc8693_form_and_never_caches_by_raw_token():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((dict(httpx.QueryParams(request.content.decode())), request.headers["authorization"]))
        return httpx.Response(200, json={"access_token": "exchanged", "expires_in": 60})

    svc = _token_service(handler)
    assert svc.exchange("user-token", "catalogue") == "exchanged"
    form, auth = seen[0]
    assert form["grant_type"] == "urn:ietf:params:oauth:grant-type:token-exchange"
    assert form["subject_token"] == "user-token" and form["audience"] == "catalogue"
    assert auth.startswith("Basic ")
    assert all("user-token" not in k for k in svc._cache)


def test_platform_with_oidc_and_service_client_acting_for_caller():
    idp_calls = []

    def idp(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/certs"):
            return httpx.Response(200, json={"keys": [JWK1]})
        form = dict(httpx.QueryParams(request.content.decode()))
        idp_calls.append(form.get("grant_type", f"{request.method} {request.url}"))
        return httpx.Response(200, json={"access_token": "for-catalogue", "expires_in": 60})

    transport = httpx.MockTransport(idp)
    original = httpx.Client.__init__

    def patched(self, *a, **kw):
        kw["transport"] = transport
        original(self, *a, **kw)

    httpx.Client.__init__ = patched
    try:
        secrets = MemorySecretStore({"hub": "s3cret"})
        settings = PlatformSettings(service="hub", egress_allowlist=("idp.example.com", "catalogue.example.com"))
        p = (Platform.builder("hub", settings)
             .with_egress(EgressPolicy(allowlist=("idp.example.com", "catalogue.example.com"),
                                       resolver=lambda h: ["93.184.216.34"]))
             .with_oidc(issuer=ISS, audience=AUD, jwks_url="https://idp.example.com/realms/sdd/certs")
             .with_oauth(token_url="https://idp.example.com/token", client_id="hub", client_secret_ref="mem://hub")
             .with_secrets(secrets).build())
        sent = {}
        catalogue = p.service_client("catalogue", "https://catalogue.example.com", audience="catalogue")
        httpx.Client.__init__ = original  # the clients above keep the mock transport; the test client must not
        catalogue._http = httpx.Client(transport=httpx.MockTransport(
            lambda r: sent.update(auth=r.headers["authorization"]) or httpx.Response(200, json={})))
        r = APIRouter()

        @r.get("/whoami")
        def whoami() -> dict:
            catalogue.request("GET", "/skus")
            return {"sub": ctxmod.current().principal.subject}

        client = TestClient(p.create_app([r]))
        res = client.get("/whoami", headers={"Authorization": f"Bearer {token()}"})
        assert res.json() == {"sub": "ada"}
        assert sent["auth"] == "Bearer for-catalogue"
        assert idp_calls == ["urn:ietf:params:oauth:grant-type:token-exchange"]
        assert "identity" not in p.simulated
        assert client.get("/whoami").status_code == 401
        # Review 0.2 #4: outside a request there is no caller to act for; never fall back to the service token.
        from platform_kernel.http import OutboundError

        with pytest.raises(OutboundError) as refused:
            catalogue.request("GET", "/skus")
        assert refused.value.error.code == "FORBIDDEN"
        p.close()
    finally:
        httpx.Client.__init__ = original


def test_oidc_host_must_be_on_the_egress_allowlist():
    from platform_kernel.platform import ConfigurationError

    with pytest.raises(ConfigurationError) as e:
        Platform.builder("hub", PlatformSettings(service="hub")).with_oidc(
            issuer=ISS, audience=AUD, jwks_url="https://idp.example.com/certs").build()
    assert "JWKS host" in str(e.value)


def test_request_context_never_prints_the_token():
    ctx = ctxmod.RequestContext(principal=ctxmod.Principal("a"), tenant=ctxmod.TenantScope(None),
                                correlation_id="c", deadline=datetime.now(UTC) + timedelta(seconds=1), token="secret")
    assert "secret" not in repr(ctx)
