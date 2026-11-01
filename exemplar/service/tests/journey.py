"""One journey through the exemplar API, recorded as the contract the web-kit's simulated provider must match.

`python exemplar/service/tests/journey.py` rewrites web/src/kit/api/conformance/exemplar-journey.json.
test_exemplar.py checks the live service still answers with the same shapes, and the web-kit's vitest suite checks
the simulated provider does, so neither side can drift alone.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

FIXTURE = Path(__file__).resolve().parents[3] / "web" / "src" / "kit" / "api" / "conformance" / "exemplar-journey.json"
ADA = {"Authorization": "Bearer demo:ada:integration-admin:t1"}
OMAR = {"Authorization": "Bearer demo:omar:integration-approver:t1"}


def spec(name: str, prefix: str) -> dict[str, Any]:
    return {"spec": {"name": name, "connector": "echo", "connector_version": "1.0.0", "config": {"prefix": prefix}}}


def at(who: dict[str, str], record: dict[str, Any]) -> dict[str, str]:
    return {**who, "If-Match": f'"{record["revision"]}"'}


def run(platform: Any, client: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    base = "/api/v1/connections"

    def keep(key: str, r: Any) -> Any:
        out[key] = {"status": r.status_code, "body": r.json()}
        return r.json()

    keep("me", client.get("/api/v1/portal/me", headers=ADA))
    keep("kinds", client.get("/api/v1/portal/kinds", headers=ADA))
    keep("plugins", client.get("/api/v1/portal/plugins", headers=ADA))
    rec = keep("created", client.post("/api/v1/connections", headers=ADA, json=spec("Customs gateway", "ZATCA")))
    cid = rec["id"]
    rec = keep("tested", client.post(f"{base}/{cid}/test", headers=at(ADA, rec)))
    rec = keep("submitted", client.post(f"{base}/{cid}/submit", headers=at(ADA, rec)))
    keep("selfApprove", client.post(f"{base}/{cid}/approve", headers=at(ADA, rec)))
    keep("approved", client.post(f"{base}/{cid}/approve", headers=at(OMAR, rec)))
    platform.relay.run_once(100)
    keep("activations", client.get("/api/v1/activations", headers=ADA))
    keep("send", client.post(f"/api/v1/connections/{cid}/send", headers=ADA, json={"payload": {"text": "D-1"}}))
    op = keep("accepted", client.post(f"{base}/{cid}/send-batch", headers=ADA,
                                      json={"payloads": [{"n": i} for i in range(3)]}))
    platform.operations.wait(op["id"])
    time.sleep(0.05)
    keep("operation", client.get(f"/api/v1/operations/{op['id']}", headers=ADA))
    keep("operations", client.get("/api/v1/operations", headers=ADA))
    keep("versions", client.get(f"/api/v1/connections/{cid}/versions", headers=ADA))
    keep("list", client.get("/api/v1/connections", headers=ADA))
    keep("forbidden", client.post("/api/v1/connections", headers=OMAR, json=spec("x", "a")))
    bad = client.post("/api/v1/connections", headers=ADA, json=spec("x", " a")).json()
    keep("failedTest", client.post(f"{base}/{bad['id']}/test", headers=at(ADA, bad)))
    keep("stale", client.post(f"/api/v1/connections/{cid}/pause", headers={**ADA, "If-Match": '"1"'}))
    keep("invalid", client.post("/api/v1/connections", headers=ADA, json={"spec": {"name": "x"}}))
    keep("batchNotActive", client.post(f"{base}/{bad['id']}/send-batch", headers=ADA, json={"payloads": [{}]}))
    keep("batchMissing", client.post(f"{base}/nope/send-batch", headers=ADA, json={"payloads": [{}]}))
    keep("batchEmpty", client.post(f"{base}/{cid}/send-batch", headers=ADA, json={"payloads": []}))
    keep("batchNoUse", client.post(f"{base}/nope/send-batch", headers=OMAR, json={"payloads": [{}]}))
    keep("pluginsApprover", client.get("/api/v1/portal/plugins", headers=OMAR))
    keep("operationsBadLimit", client.get("/api/v1/operations?limit=0", headers=ADA))
    keep("anon", client.get("/api/v1/portal/me"))
    return out


def shape(v: Any) -> Any:
    """Keys and value types, recursively; lists by their first item. Values themselves do not matter."""
    if isinstance(v, dict):
        return {k: shape(x) for k, x in sorted(v.items())}
    if isinstance(v, list):
        return [shape(v[0])] if v else []
    return type(v).__name__


if __name__ == "__main__":
    from exemplar_connections.wiring import build
    from fastapi.testclient import TestClient
    from platform_kernel.config import PlatformSettings

    platform, app = build(PlatformSettings(service="connections", allow_demo=True))
    try:
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        body = json.dumps(run(platform, TestClient(app)), indent=1, ensure_ascii=False)
        FIXTURE.write_text(body + "\n", encoding="utf-8")
        print(f"wrote {FIXTURE}")
    finally:
        platform.close()
