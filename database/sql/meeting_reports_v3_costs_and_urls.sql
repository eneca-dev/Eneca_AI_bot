-- Add cost tracking and DOCX artifact URLs to meeting_reports.
-- Apply once to the project pointed at by SUPABASE_MEETINGS_URL.
--
-- Adds:
--   * llm_cost_usd       — OpenAI Chat Completions (TeamsAgent) cost in USD
--   * whisper_cost_usd   — OpenAI Whisper transcription cost in USD
--   * recall_cost_usd    — Recall.ai recording bot cost in USD
--   * total_cost_usd     — generated column = llm + whisper + recall
--   * protocol_docx_url  — Supabase Storage public URL of protocol.docx
--   * transcript_docx_url — Supabase Storage public URL of transcript.docx
--
-- All cost columns use numeric(10,4) — USD with sub-cent precision (e.g. 0.0234).

alter table meeting_reports
    add column if not exists llm_cost_usd        numeric(10,4),
    add column if not exists whisper_cost_usd    numeric(10,4),
    add column if not exists recall_cost_usd     numeric(10,4),
    add column if not exists protocol_docx_url   text,
    add column if not exists transcript_docx_url text;

-- Generated column for fast "total cost" filters in the dashboard.
alter table meeting_reports
    drop column if exists total_cost_usd;

alter table meeting_reports
    add column total_cost_usd numeric(10,4)
    generated always as (
        coalesce(llm_cost_usd, 0)
      + coalesce(whisper_cost_usd, 0)
      + coalesce(recall_cost_usd, 0)
    ) stored;

create index if not exists meeting_reports_total_cost_idx
    on meeting_reports(total_cost_usd desc);
