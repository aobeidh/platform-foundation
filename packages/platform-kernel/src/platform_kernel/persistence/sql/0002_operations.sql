-- Long-running operations and saga state (P39, I12). One row per operation; state is saved after every saga step.
create table if not exists operation (
  id text primary key,
  kind text not null,
  tenant_id text,
  status text not null check (status in ('pending', 'running', 'stalled', 'succeeded', 'failed', 'cancelled')),
  progress int not null default 0 check (progress between 0 and 100),
  input jsonb not null,
  state jsonb not null default '{}',
  result jsonb,
  error jsonb,
  cancel_requested boolean not null default false,
  created_by text not null,
  created_roles jsonb not null default '[]',
  correlation_id text,
  lease_owner text,
  lease_until timestamptz,
  created_at timestamptz not null,
  updated_at timestamptz not null
);
create index if not exists operation_unfinished on operation (status) where status in ('pending', 'running', 'stalled');

alter table operation enable row level security;
alter table operation force row level security;
do $$ begin
  if not exists (select 1 from pg_policies where schemaname = current_schema() and tablename = 'operation') then
    create policy tenant_scope on operation using (
      coalesce(current_setting('app.scope', true), '') = 'platform'
      or tenant_id = current_setting('app.tenant', true));
  end if;
end $$;
