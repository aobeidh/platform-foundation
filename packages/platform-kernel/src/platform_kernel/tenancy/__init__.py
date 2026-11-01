"""Layer 2. Tenant scope resolution and tagging (P22). The database applies it again with row-level security."""
from ..context import TenantScope
from .scope import current_scope, require_tenant, tenant_key

__all__ = ["TenantScope", "current_scope", "require_tenant", "tenant_key"]
