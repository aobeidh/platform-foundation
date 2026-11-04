-- Kernel tables for SQLite (ADR 0008), the same shape as ../0001_kernel.sql (spec: F9, P18, P19, P41, P17, P13).
-- Timestamps are UTC text in one fixed-width format (persistence.sqlite.to_text), so text order is time order.
-- JSON is text. SQLite has no row-level security: the providers apply the tenant scope in code (P22).
create table if not exists outbox (
  id text primary key,
  type text not null,
  subject text,
  tenant_id text,
  occurred_at text not null,
  envelope text not null,
  sent_at text,
  attempts integer not null default 0,
  last_error text
);
create index if not exists outbox_unsent on outbox (occurred_at, id) where sent_at is null;

create table if not exists inbox (
  consumer text not null,
  event_id text not null,
  processed_at text not null,
  primary key (consumer, event_id)
);

create table if not exists dead_letter (
  id text primary key,
  consumer text not null,
  kind text not null check (kind in ('invalid', 'dead')),
  reason text not null,
  envelope text not null,
  at text not null
);

create table if not exists idempotency_key (
  tenant_id text not null default '',
  key text not null,
  request_hash text not null,
  status text not null check (status in ('in_progress', 'completed')),
  status_code integer,
  response text,
  created_at text not null,
  primary key (tenant_id, key)
);

create table if not exists audit_record (
  stream text not null,
  seq integer not null,
  at text not null,
  tenant_id text,
  entry text not null,
  prev_hash text not null,
  hash text not null,
  primary key (stream, seq)
);

create table if not exists governed_record (
  kind text not null,
  id text not null,
  tenant_id text,
  status text not null,
  current_version integer not null,
  active_version integer,
  revision integer not null,
  created_at text not null,
  updated_at text not null,
  primary key (kind, id)
);

-- edited_by is a JSON array of subjects. P14: nobody who authored, edited or submitted a version may approve it.
-- The check covers the creator and the submitter; a check constraint cannot hold a subquery, so the triggers below
-- refuse an editor. The store enforces the same rule in code before every write.
create table if not exists governed_version (
  kind text not null,
  id text not null,
  version integer not null,
  tenant_id text,
  status text not null,
  spec text not null,
  maker_checker integer not null check (maker_checker in (0, 1)),
  created_by text not null,
  submitted_by text,
  approved_by text,
  test_result text,
  edited_by text not null default '[]',
  created_at text not null,
  primary key (kind, id, version),
  constraint maker_checker_second_person check (
    not maker_checker or approved_by is null or (
      approved_by <> created_by
      and approved_by is not submitted_by))
);

create trigger if not exists maker_checker_second_person_insert before insert on governed_version
when new.maker_checker and new.approved_by is not null
  and exists (select 1 from json_each(new.edited_by) where value = new.approved_by)
begin
  select raise(abort, 'maker_checker_second_person: the approver edited this version');
end;

create trigger if not exists maker_checker_second_person_update before update on governed_version
when new.maker_checker and new.approved_by is not null
  and exists (select 1 from json_each(new.edited_by) where value = new.approved_by)
begin
  select raise(abort, 'maker_checker_second_person: the approver edited this version');
end;
