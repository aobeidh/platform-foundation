-- The SQLite version of ../0001_activations.sql (ADR 0008 in the foundation). SQLite has no row-level security:
-- the repository applies the tenant scope in code. Timestamps are UTC text written by persistence.sqlite.to_text.
create table if not exists activations (
  event_id text primary key,
  connection_id text not null,
  version integer not null,
  tenant_id text,
  activated_at text not null
);
