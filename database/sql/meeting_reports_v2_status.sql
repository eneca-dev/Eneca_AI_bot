-- Add status tracking to meeting_reports.
-- Apply once to the project pointed at by SUPABASE_MEETINGS_URL.
--
-- Adds:
--   * status        — 'processing' | 'done' | 'error' (check constraint, default 'done')
--   * error_message — error description when status='error'
--   * relaxes NOT NULL on report / subject / meeting_date so we can persist a row
--     at the start of processing (before transcript & report exist).

alter table meeting_reports
    add column if not exists status        text not null default 'done',
    add column if not exists error_message text;

alter table meeting_reports
    drop constraint if exists meeting_reports_status_check;

alter table meeting_reports
    add constraint meeting_reports_status_check
    check (status in ('processing', 'done', 'error'));

create index if not exists meeting_reports_status_idx
    on meeting_reports(status);

-- Allow rows to exist before the report / subject / date are known.
-- They will be filled in by the UPDATE that flips status to 'done'.
alter table meeting_reports alter column report       drop not null;
alter table meeting_reports alter column subject      drop not null;
alter table meeting_reports alter column meeting_date drop not null;
