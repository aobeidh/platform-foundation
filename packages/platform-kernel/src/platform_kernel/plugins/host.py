"""One plugin host for every plugin kind (F12). Kinds differ only in their SPI.

Signature verification is a port. Milestone 0.1 ships a publisher allowlist and a development-only verifier that
accepts unsigned plugins; Sigstore verification is a later provider behind the same port (P38)."""
from __future__ import annotations

import contextvars
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import Any, Protocol

import jsonschema
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import Version
from platform_plugin_sdk import Descriptor, FieldError, Plugin

from ..core import DomainError, Err, Ok, Result
from ..observability import get_logger, meter

log = get_logger("platform.plugins")
_calls = meter.create_histogram("plugin.call.duration", unit="ms", description="Plugin call duration")


class SignatureVerifier(Protocol):
    simulated: bool

    def verify(self, descriptor: Descriptor, distribution: str | None) -> bool: ...


class PublisherAllowlistVerifier:
    """Accepts plugins whose descriptor names an allowed publisher. Interim provider until Sigstore."""

    simulated = False

    def __init__(self, publishers: set[str]) -> None:
        self._publishers = publishers

    def verify(self, descriptor: Descriptor, distribution: str | None) -> bool:
        return descriptor.publisher in self._publishers


class AllowUnsignedVerifier:
    """Development only; refused in production by the Platform builder (F23)."""

    simulated = True

    def verify(self, descriptor: Descriptor, distribution: str | None) -> bool:
        return True


@dataclass(frozen=True)
class Registration:
    ok: bool
    id: str
    version: str
    reason: str | None = None


class PluginHost:
    def __init__(self, kind: str, spi_version: str, spi: type, verifier: SignatureVerifier,
                 call_timeout_seconds: float = 10.0, max_workers: int = 8) -> None:
        self.kind, self.spi_version, self.spi = kind, Version(spi_version), spi
        self._verifier = verifier
        self._timeout = call_timeout_seconds
        self._items: dict[tuple[str, str], Any] = {}
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix=f"plugin-{kind}")

    # Registration -----------------------------------------------------------------------------------------------

    def register(self, plugin: Any, distribution: str | None = None) -> Registration:
        d: Descriptor | None = getattr(plugin, "descriptor", None)
        if not isinstance(d, Descriptor):
            return Registration(False, "?", "?", "PLUGIN_DESCRIPTOR_INVALID")
        if d.kind != self.kind:
            return Registration(False, d.id, d.version, f"PLUGIN_KIND_MISMATCH: {d.kind}")
        if not isinstance(plugin, Plugin) or not isinstance(plugin, self.spi):
            return Registration(False, d.id, d.version, "PLUGIN_SPI_NOT_IMPLEMENTED")
        try:
            compatible = self.spi_version in SpecifierSet(d.spi)
        except InvalidSpecifier:
            compatible = False
        if not compatible:
            return Registration(False, d.id, d.version, f"SPI_INCOMPATIBLE: host {self.spi_version}, plugin {d.spi}")
        try:
            jsonschema.Draft202012Validator.check_schema(d.config_schema)
        except jsonschema.SchemaError as exc:
            return Registration(False, d.id, d.version, f"PLUGIN_CONFIG_SCHEMA_INVALID: {exc.message}")
        if not self._verifier.verify(d, distribution):
            return Registration(False, d.id, d.version, "PLUGIN_SIGNATURE_INVALID")
        self._items[(d.id, d.version)] = plugin
        log.info("plugin.registered", kind=self.kind, plugin=d.id, version=d.version)
        return Registration(True, d.id, d.version)

    def discover(self, group: str) -> list[Registration]:
        results = []
        for ep in entry_points(group=group):
            try:
                factory = ep.load()
                plugin = factory()
            except Exception as exc:  # noqa: BLE001 - a broken plugin must not stop the host
                results.append(Registration(False, ep.name, "?", f"PLUGIN_LOAD_FAILED: {exc}"))
                continue
            results.append(self.register(plugin, ep.dist.name if ep.dist else None))
        return results

    # Lookup -----------------------------------------------------------------------------------------------------

    def descriptors(self) -> list[Descriptor]:
        return sorted((p.descriptor for p in self._items.values()), key=lambda d: (d.id, Version(d.version)))

    def get(self, id: str, version: str | None = None) -> Result[Any, DomainError]:
        if version is not None:
            p = self._items.get((id, version))
        else:
            candidates = [(Version(v), p) for (i, v), p in self._items.items() if i == id]
            p = max(candidates, key=lambda c: c[0])[1] if candidates else None
        if p is None:
            return Err(DomainError("PLUGIN_NOT_FOUND", f"No {self.kind} plugin {id}"
                                                       f"{' ' + version if version else ''} is registered."))
        return Ok(p)

    # Calls ------------------------------------------------------------------------------------------------------

    def validate_config(self, id: str, version: str, config: dict[str, Any]) -> Result[None, DomainError]:
        got = self.get(id, version)
        if not got.ok:
            return got
        plugin = got.value
        errors: list[FieldError] = []
        validator = jsonschema.Draft202012Validator(plugin.descriptor.config_schema)
        for e in validator.iter_errors(config):
            pointer = "/" + "/".join(str(p) for p in e.absolute_path)
            errors.append(FieldError(pointer=pointer if pointer != "/" else "", code="schema", message=e.message))
        if not errors:
            called = self.call(id, version, "validate", config)
            if not called.ok:
                return called
            errors.extend(called.value)
        if errors:
            return Err(DomainError("VALIDATION_FAILED", f"The {self.kind} configuration is not valid.",
                                   tuple(errors)))
        return Ok(None)

    def call(self, id: str, version: str, method: str, *args: Any,
             timeout: float | None = None) -> Result[Any, DomainError]:
        """Run a plugin method with a timeout; any failure becomes PLUGIN_FAILED with the plugin id."""
        import time

        got = self.get(id, version)
        if not got.ok:
            return got
        fn: Callable[..., Any] = getattr(got.value, method)
        started = time.perf_counter()
        # Copy the request context into the worker thread (F8): deadline, tenant and correlation reach the plugin.
        future = self._pool.submit(contextvars.copy_context().run, fn, *args)
        try:
            return Ok(future.result(timeout=timeout or self._timeout))
        except FutureTimeout:
            return Err(DomainError("PLUGIN_FAILED", f"{self.kind} plugin {id} {version} did not answer in time."))
        except Exception as exc:  # noqa: BLE001
            log.warning("plugin.failed", kind=self.kind, plugin=id, version=version, method=method, error=str(exc))
            return Err(DomainError("PLUGIN_FAILED", f"{self.kind} plugin {id} {version} failed: {exc}"))
        finally:
            _calls.record((time.perf_counter() - started) * 1000, {"plugin": id, "kind": self.kind})

    def close(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
