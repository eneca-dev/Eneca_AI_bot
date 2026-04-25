"""Supabase client for the `meeting_reports` table.

Points at a dedicated Supabase project (SUPABASE_MEETINGS_URL), separate from
the CHAT and RAG projects. Uses a service-role key to bypass RLS for bot writes.

Two persistence flows are supported:

1. **Async two-phase flow** — used by the Recall webhook handler:
       start_meeting_processing(bot_id)        # row appears with status='processing'
       complete_meeting_report(bot_id, ...)    # status='done' + report + transcript
       mark_meeting_error(bot_id, msg)         # status='error' + error_message

2. **Sync single-shot flow** — used by /api/teams/process-meeting:
       upsert_meeting_report(report, ..., status='done')

Fails open: missing credentials → client is a no-op, all methods return None.
Persistence failures must never break the Teams message delivery flow.
"""
from typing import Optional, Dict, Any

from supabase import create_client, Client
from loguru import logger

from core.config import settings


TABLE = "meeting_reports"

STATUS_PROCESSING = "processing"
STATUS_DONE = "done"
STATUS_ERROR = "error"

_ERROR_MESSAGE_MAX_LEN = 2000


class MeetingsDBClient:
    """Singleton Supabase client for meeting report persistence."""

    def __init__(self):
        self.client: Optional[Client] = None
        self._initialize()

    def _initialize(self):
        url = settings.supabase_meetings_url
        key = settings.supabase_meetings_service_key
        if not url or not key:
            logger.warning(
                "Meetings Supabase credentials not configured "
                "(SUPABASE_MEETINGS_URL / SUPABASE_MEETINGS_SERVICE_KEY) — "
                "report persistence disabled"
            )
            return

        try:
            self.client = create_client(url, key)
            logger.info("Meetings Supabase client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Meetings Supabase client: {e}")
            self.client = None

    def is_available(self) -> bool:
        return self.client is not None

    # ------------------------------------------------------------------
    # Async two-phase flow (Recall webhook)
    # ------------------------------------------------------------------

    def start_meeting_processing(
        self,
        recall_bot_id: str,
        subject: Optional[str] = None,
        meeting_date: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Create a row marking that we have started processing this meeting.

        Idempotent: a duplicate `recall_bot_id` (e.g. a Recall webhook retry)
        is swallowed and the existing row returned. The existing row is NOT
        overwritten — important so a retry after `complete_meeting_report` does
        not reset status='done' back to 'processing'.
        """
        if not self.is_available():
            logger.warning("Meetings DB client unavailable — skipping start_meeting_processing")
            return None

        row = {
            "recall_bot_id": recall_bot_id,
            "status": STATUS_PROCESSING,
            "subject": subject,
            "meeting_date": meeting_date,
        }

        try:
            response = self.client.table(TABLE).insert(row).execute()
            if response.data:
                saved = response.data[0]
                logger.info(
                    f"Meeting processing started: id={saved.get('id')}, "
                    f"recall_bot_id={recall_bot_id}"
                )
                return saved
            return None
        except Exception as e:
            # Most likely cause: unique constraint on recall_bot_id — webhook retry.
            logger.info(
                f"start_meeting_processing: row already exists for "
                f"recall_bot_id={recall_bot_id} (likely webhook retry): {e}"
            )
            return self.get_meeting_report_by_bot_id(recall_bot_id)

    def complete_meeting_report(
        self,
        recall_bot_id: str,
        report: Dict[str, Any],
        transcript: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Mark a meeting as done and store the generated report and transcript.

        If the row was never created via `start_meeting_processing` (defensive
        path — e.g. processing-row insert silently failed), falls back to a
        plain UPSERT so the report is still persisted.
        """
        if not self.is_available():
            logger.warning("Meetings DB client unavailable — skipping complete_meeting_report")
            return None

        update_row = {
            "status": STATUS_DONE,
            "subject": report.get("subject"),
            "meeting_date": report.get("date"),
            "report": report,
            "transcript": transcript,
            "error_message": None,
        }

        try:
            response = (
                self.client.table(TABLE)
                .update(update_row)
                .eq("recall_bot_id", recall_bot_id)
                .execute()
            )
            if response.data:
                saved = response.data[0]
                logger.info(
                    f"Meeting report completed: id={saved.get('id')}, "
                    f"recall_bot_id={recall_bot_id}"
                )
                return saved

            logger.warning(
                f"complete_meeting_report: no existing row for "
                f"recall_bot_id={recall_bot_id} — falling back to UPSERT"
            )
            return self.upsert_meeting_report(
                report=report,
                transcript=transcript,
                recall_bot_id=recall_bot_id,
                status=STATUS_DONE,
            )
        except Exception as e:
            logger.error(
                f"Failed to complete meeting report (recall_bot_id={recall_bot_id}): {e}"
            )
            return None

    def mark_meeting_error(
        self,
        recall_bot_id: str,
        error_message: str,
    ) -> Optional[Dict[str, Any]]:
        """Mark a meeting as failed and store the error message.

        If the row does not exist yet, creates a minimal error row so the
        failure is still visible in the dashboard.
        """
        if not self.is_available():
            logger.warning("Meetings DB client unavailable — skipping mark_meeting_error")
            return None

        truncated = (error_message or "")[:_ERROR_MESSAGE_MAX_LEN]
        update_row = {
            "status": STATUS_ERROR,
            "error_message": truncated,
        }

        try:
            response = (
                self.client.table(TABLE)
                .update(update_row)
                .eq("recall_bot_id", recall_bot_id)
                .execute()
            )
            if response.data:
                saved = response.data[0]
                logger.info(
                    f"Meeting marked as error: id={saved.get('id')}, "
                    f"recall_bot_id={recall_bot_id}"
                )
                return saved

            logger.warning(
                f"mark_meeting_error: no existing row for recall_bot_id={recall_bot_id} "
                "— inserting a minimal error row"
            )
            insert_row = {
                "recall_bot_id": recall_bot_id,
                "status": STATUS_ERROR,
                "error_message": truncated,
            }
            ins = self.client.table(TABLE).insert(insert_row).execute()
            return ins.data[0] if ins.data else None
        except Exception as e:
            logger.error(
                f"Failed to mark meeting as error (recall_bot_id={recall_bot_id}): {e}"
            )
            return None

    # ------------------------------------------------------------------
    # Sync single-shot flow (/api/teams/process-meeting)
    # ------------------------------------------------------------------

    def upsert_meeting_report(
        self,
        report: Dict[str, Any],
        transcript: Optional[Dict[str, Any]] = None,
        recall_bot_id: Optional[str] = None,
        status: str = STATUS_DONE,
    ) -> Optional[Dict[str, Any]]:
        """Persist a meeting report in one shot (no separate processing phase).

        When `recall_bot_id` is provided, UPSERT on that column — makes the
        Recall webhook idempotent. Without it, falls back to a plain INSERT.
        """
        if not self.is_available():
            logger.warning("Meetings DB client unavailable — skipping persistence")
            return None

        row = {
            "recall_bot_id": recall_bot_id,
            "status": status,
            "subject": report.get("subject"),
            "meeting_date": report.get("date"),
            "report": report,
            "transcript": transcript,
        }

        try:
            if recall_bot_id:
                response = (
                    self.client.table(TABLE)
                    .upsert(row, on_conflict="recall_bot_id")
                    .execute()
                )
            else:
                response = self.client.table(TABLE).insert(row).execute()

            if response.data:
                saved = response.data[0]
                logger.info(
                    f"Meeting report persisted: id={saved.get('id')}, "
                    f"recall_bot_id={recall_bot_id}, status={status}, "
                    f"subject={saved.get('subject')!r}"
                )
                return saved

            logger.warning("Meeting report persist returned no data")
            return None

        except Exception as e:
            logger.error(
                f"Failed to persist meeting report (recall_bot_id={recall_bot_id}): {e}"
            )
            return None

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_meeting_report_by_bot_id(self, recall_bot_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a persisted meeting report by its Recall bot id."""
        if not self.is_available():
            return None
        try:
            response = (
                self.client.table(TABLE)
                .select("*")
                .eq("recall_bot_id", recall_bot_id)
                .limit(1)
                .execute()
            )
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(
                f"Failed to fetch meeting report for recall_bot_id={recall_bot_id}: {e}"
            )
            return None


meetings_db_client = MeetingsDBClient()
