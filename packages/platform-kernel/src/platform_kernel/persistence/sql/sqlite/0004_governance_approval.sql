-- Approval policy (0.4): who tested a version and when, and why it was returned. Expand only (P32).
-- SQLite has no "add column if not exists"; the runner applies this file once.
alter table governed_version add column tested_by text;
alter table governed_version add column tested_at text;
alter table governed_version add column reason text;
