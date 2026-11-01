create table if not exists activations (
  event_id text primary key,
  connection_id text not null,
  version int not null,
  tenant_id text,
  activated_at timestamptz not null
);
alter table activations enable row level security;
alter table activations force row level security;
do $$ begin
  if not exists (select 1 from pg_policies where schemaname = current_schema() and tablename = 'activations') then
    create policy tenant_scope on activations using (
      coalesce(current_setting('app.scope', true), '') = 'platform'
      or tenant_id = current_setting('app.tenant', true));
  end if;
end $$;
