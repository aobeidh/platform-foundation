-- Long-running operations and saga state for SQLite (P39, I12), the same shape as ../0002_operations.sql.
create table if not exists operation (
  id text primary key,
  kind text not null,
  tenant_id text,
  status text not null check (status in ('pending', 'running', 'stalled', 'succeeded', 'failed', 'cancelled')),
  progress integer not null default 0 check (progress between 0 and 100),
  input text not null,
  state text not null default '{}',
  result text,
  error text,
  cancel_requested integer not null default 0 check (cancel_requested in (0, 1)),
  created_by text not null,
  created_roles text not null default '[]',
  correlation_id text,
  lease_owner text,
  lease_until text,
  created_at text not null,
  updated_at text not null
);
create index if not exists operation_unfinished on operation (status) where status in ('pending', 'running', 'stalled');
