-- Add inviter identity and full meeting start timestamp to meeting_reports.
-- Apply once to the project pointed at by SUPABASE_MEETINGS_URL.
--
-- Adds:
--   * invited_by_aad_object_id — AAD ObjectId of the Teams user who sent the
--                                meeting link to the bot. Stable across name
--                                changes; useful for analytics / filters.
--   * invited_by_name          — Display name at the moment of invitation.
--                                Captured separately because aadObjectId may
--                                be absent for guest / external users.
--   * meeting_started_at       — Full timestamptz of when the bot joined the
--                                call (Recall `join_at`). Complements
--                                `meeting_date` which only stores the date.
--
-- Backfill is intentionally NOT performed — old rows keep NULLs.

alter table meeting_reports
    add column if not exists invited_by_aad_object_id text,
    add column if not exists invited_by_name          text,
    add column if not exists meeting_started_at       timestamptz;

create index if not exists meeting_reports_meeting_started_at_idx
    on meeting_reports(meeting_started_at desc);
