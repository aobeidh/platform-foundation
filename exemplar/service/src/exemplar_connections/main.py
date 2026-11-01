"""Process entry: `uvicorn exemplar_connections.main:app`."""
from __future__ import annotations

from platform_kernel.observability import configure_logging

from .wiring import SERVICE, build

configure_logging(SERVICE, "0.1.0", "development")
platform, app = build()
