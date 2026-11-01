"""PolicyEngine port with an in-process provider. OPA is a later provider behind the same port."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

from ..context import Principal

_CAP = re.compile(r"^[a-z][a-z0-9-]*:[a-z][a-z0-9-]*$")


@dataclass(frozen=True)
class Capability:
    name: str
    display: dict[str, str]

    def __post_init__(self) -> None:
        if not _CAP.match(self.name):
            raise ValueError(f"capability {self.name!r} must look like 'area:verb'")
        if "en" not in self.display:
            raise ValueError(f"capability {self.name!r} needs an English display name")


class CapabilityCatalog:
    def __init__(self) -> None:
        self._caps: dict[str, Capability] = {}

    def declare(self, name: str, en: str, **other_languages: str) -> Capability:
        cap = Capability(name, {"en": en, **other_languages})
        existing = self._caps.get(name)
        if existing and existing != cap:
            raise ValueError(f"capability {name!r} declared twice with different names")
        self._caps[name] = cap
        return cap

    def __contains__(self, name: str) -> bool:
        return name in self._caps

    def names(self) -> frozenset[str]:
        return frozenset(self._caps)


@dataclass(frozen=True)
class Role:
    name: str
    capabilities: frozenset[str]
    scope: str = "platform"  # "platform" or "tenant"


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    held_back: frozenset[str] = field(default=frozenset())


class PolicyEngine(Protocol):
    def decide(self, principal: Principal, capability: str) -> Decision: ...
    def capabilities(self, principal: Principal) -> frozenset[str]: ...


class InProcessPolicyEngine:
    """Roles map to capabilities. A separation-of-duties rule names two capabilities: whoever would hold both
    through their roles gets neither (P21)."""

    def __init__(self, catalog: CapabilityCatalog, roles: list[Role],
                 separation_of_duties: list[tuple[str, str]] | None = None) -> None:
        self._catalog = catalog
        self._roles = {r.name: r for r in roles}
        for r in roles:
            unknown = r.capabilities - catalog.names()
            if unknown:
                raise ValueError(f"role {r.name!r} grants unknown capabilities: {', '.join(sorted(unknown))}")
        self._sod = list(separation_of_duties or [])

    def _raw(self, principal: Principal) -> frozenset[str]:
        caps: set[str] = set()
        for name in principal.roles:
            role = self._roles.get(name)
            if role is None:
                continue
            if role.scope == "tenant" and principal.tenant is None:
                continue
            if role.scope == "platform" and principal.tenant is not None:
                continue
            caps |= role.capabilities
        return frozenset(caps)

    def capabilities(self, principal: Principal) -> frozenset[str]:
        caps = set(self._raw(principal))
        for a, b in self._sod:
            if a in caps and b in caps:
                caps -= {a, b}
        return frozenset(caps)

    def decide(self, principal: Principal, capability: str) -> Decision:
        if capability not in self._catalog:
            return Decision(False, f"capability {capability!r} is not declared")
        raw = self._raw(principal)
        effective = self.capabilities(principal)
        if capability in effective:
            return Decision(True, "granted by role")
        if capability in raw:
            return Decision(False, "withheld by a separation-of-duties rule", frozenset({capability}))
        return Decision(False, "no role grants this capability")
