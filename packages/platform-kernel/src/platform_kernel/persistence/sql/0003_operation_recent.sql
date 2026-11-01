-- Listing operations newest first, per tenant and per creator (GET /api/v1/operations).
create index if not exists operation_recent on operation (tenant_id, created_at desc);
create index if not exists operation_recent_by_creator on operation (tenant_id, created_by, created_at desc);
