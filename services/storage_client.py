"""Supabase Storage client for meeting artifacts (DOCX files).

The bucket configured via SUPABASE_MEETINGS_BUCKET (default `meeting-protocols`)
must exist as a **public** bucket — created once via the Supabase Dashboard
(Storage → New bucket → Public ON).

Uploads are namespaced by Recall bot id, so a single recording can have
multiple artifacts (`<bot_id>/protocol.docx`, `<bot_id>/transcript.docx`).
Re-uploading the same path overwrites (`upsert=true`) — important for
webhook retries.

Fails open: missing credentials → no-op, `upload_meeting_artifact` returns None.
"""
from typing import Optional

from supabase import create_client, Client
from loguru import logger

from core.config import settings


class StorageClient:
    """Singleton wrapper around Supabase Storage for meeting artifacts."""

    def __init__(self):
        self.client: Optional[Client] = None
        self._initialize()

    def _initialize(self):
        url = settings.supabase_meetings_url
        key = settings.supabase_meetings_service_key
        if not url or not key:
            logger.warning(
                "Meetings Supabase credentials not configured — "
                "DOCX upload disabled"
            )
            return
        try:
            self.client = create_client(url, key)
            logger.info(
                f"Storage client initialized (bucket={settings.supabase_meetings_bucket!r})"
            )
        except Exception as e:
            logger.error(f"Failed to initialize Storage client: {e}")
            self.client = None

    @property
    def is_available(self) -> bool:
        return self.client is not None

    @property
    def bucket(self) -> str:
        return settings.supabase_meetings_bucket

    def upload_meeting_artifact(
        self,
        recall_bot_id: str,
        filename: str,
        content_bytes: bytes,
        content_type: str = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
    ) -> Optional[str]:
        """Upload `content_bytes` to `<bucket>/<recall_bot_id>/<filename>`.

        Returns the public URL on success, None on any failure.
        """
        if not self.is_available:
            logger.warning("Storage client unavailable — skipping artifact upload")
            return None
        if not recall_bot_id or not filename:
            logger.error(
                f"upload_meeting_artifact: missing recall_bot_id or filename "
                f"(bot_id={recall_bot_id!r}, filename={filename!r})"
            )
            return None

        path = f"{recall_bot_id}/{filename}"

        try:
            self.client.storage.from_(self.bucket).upload(
                path=path,
                file=content_bytes,
                file_options={
                    "content-type": content_type,
                    "upsert": "true",
                },
            )
            public_url = (
                self.client.storage.from_(self.bucket).get_public_url(path)
            )
            logger.info(
                f"Uploaded artifact: bucket={self.bucket} path={path} "
                f"size={len(content_bytes)}"
            )
            return public_url
        except Exception as e:
            logger.error(
                f"Failed to upload artifact {self.bucket}/{path}: {e}"
            )
            return None


storage_client = StorageClient()
