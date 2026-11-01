-- Approval policy (0.4): who tested a version and when, and why it was returned. Expand only (P32).
alter table governed_version add column if not exists tested_by text;
alter table governed_version add column if not exists tested_at timestamptz;
alter table governed_version add column if not exists reason text;
