-- Add the inviter's email to meeting_reports.
-- Apply once to the project pointed at by SUPABASE_MEETINGS_URL.
--
-- Adds:
--   * invited_by_email — email of the Teams user who sent the meeting link to
--                        the bot. Resolved from Microsoft Graph (mail, falling
--                        back to userPrincipalName) by the inviter's
--                        invited_by_aad_object_id. Always stored lowercase so
--                        the app can match it against profiles.email (which is
--                        lowercase) with an exact comparison.
--
-- Backfill is intentionally NOT performed — old rows keep NULLs.

alter table meeting_reports
    add column if not exists invited_by_email text;

create index if not exists meeting_reports_invited_by_email_idx
    on meeting_reports(invited_by_email);
