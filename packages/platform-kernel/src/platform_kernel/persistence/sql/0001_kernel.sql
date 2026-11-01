-- Kernel tables, created in every service schema by the migration runner (spec: F9, P18, P19, P41, P17, P13).
create table if not exists outbox (
  id text primary key,
  type text not null,
  subject text,
  tenant_id text,
  occurred_at timestamptz not null,
  envelope jsonb not null,
  sent_at timestamptz,
  attempts int not null default 0,
  last_error text
);
create index if not exists outbox_unsent on outbox (occurred_at, id) where sent_at is null;

create table if not exists inbox (
  consumer text not null,
  event_id text not null,
  processed_at timestamptz not null default now(),
  primary key (consumer, event_id)
);

create table if not exists dead_letter (
  id text primary key,
  consumer text not null,
  kind text not null check (kind in ('invalid', 'dead')),
  reason text not null,
  envelope jsonb not null,
  at timestamptz not null default now()
);

create table if not exists idempotency_key (
  tenant_id text not null default '',
  key text not null,
  request_hash text not null,
  status text not null check (status in ('in_progress', 'completed')),
  status_code int,
  response jsonb,
  created_at timestamptz not null default now(),
  primary key (tenant_id, key)
);

create table if not exists audit_record (
  stream text not null,
  seq bigint not null,
  at timestamptz not null,
  tenant_id text,
  entry jsonb not null,
  prev_hash text not null,
  hash text not null,
  primary key (stream, seq)
);

create table if not exists governed_record (
  kind text not null,
  id text not null,
  tenant_id text,
  status text not null,
  current_version int not null,
  active_version int,
  revision int not null,
  created_at timestamptz not null,
  updated_at timestamptz not null,
  primary key (kind, id)
);

create table if not exists governed_version (
  kind text not null,
  id text not null,
  version int not null,
  tenant_id text,
  status text not null,
  spec jsonb not null,
  maker_checker boolean not null,
  created_by text not null,
  submitted_by text,
  approved_by text,
  test_result jsonb,
  edited_by text[] not null default '{}',
  created_at timestamptz not null,
  primary key (kind, id, version),
  -- P14: nobody who authored, edited or submitted a version may approve it.
  constraint maker_checker_second_person check (
    not maker_checker or approved_by is null or (
      approved_by <> created_by
      and approved_by is distinct from submitted_by
      and not (approved_by = any (edited_by))))
);

alter table governed_record enable row level security;
alter table governed_record force row level security;
alter table governed_version enable row level security;
alter table governed_version force row level security;
do $$ begin
  if not exists (select 1 from pg_policies where schemaname = current_schema() and tablename = 'governed_record') then
    create policy tenant_scope on governed_record using (
      coalesce(current_setting('app.scope', true), '') = 'platform'
      or tenant_id = current_setting('app.tenant', true));
  end if;
  if not exists (select 1 from pg_policies where schemaname = current_schema() and tablename = 'governed_version') then
    create policy tenant_scope on governed_version using (
      coalesce(current_setting('app.scope', true), '') = 'platform'
      or tenant_id = current_setting('app.tenant', true));
  end if;
end $$;
