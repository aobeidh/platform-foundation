"""Layer 2. The error catalog (P51): status, retryable flag, message key, explanation, remedy."""
from .catalog import CatalogEntry, ErrorCatalog, kernel_catalog

__all__ = ["CatalogEntry", "ErrorCatalog", "kernel_catalog"]
