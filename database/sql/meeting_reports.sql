-- Meeting protocols storage.
-- Apply to the project pointed at by SUPABASE_MEETINGS_URL (separate from RAG / CHAT projects).
-- Run once in the Supabase SQL Editor.

create extension if not exists pgcrypto;

create table if not exists meeting_reports (
    id              uuid primary key default gen_random_uuid(),
    created_at      timestamptz not null default now(),

    -- Used to deduplicate Recall webhook retries and to link the row back to the Recall bot.
    recall_bot_id   text unique,

    -- Denormalised from `report` so the UI can build a list view without reading JSONB.
    subject         text not null,
    meeting_date    date not null,

    -- Full MeetingReport (Pydantic model_dump). Source of truth for rendering.
    report          jsonb not null,

    -- Full MeetingTranscript (segments with speakers and timestamps).
    transcript      jsonb
);

create index if not exists meeting_reports_meeting_date_idx
    on meeting_reports(meeting_date desc);
