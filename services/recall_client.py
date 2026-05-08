"""Client for Recall.ai API — sends bots to meetings and fetches recordings"""
import httpx
import tempfile
import os
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urlunparse
from loguru import logger
from core.config import settings


# How long an in-memory meeting lock stays valid before we assume the previous
# bot is gone and a fresh join is allowed. Three hours covers a typical long
# meeting with margin; the lock is also released proactively from the Recall
# webhook on bot.done / fatal events.
MEETING_LOCK_TTL_SECONDS = 3 * 3600

# Hosts whose query string is purely session/context noise — strip it entirely
# so that the same meeting opened from different invitations collapses to one
# canonical key.
_HOSTS_WITH_DISPOSABLE_QUERY = {
    "teams.microsoft.com",
    "teams.live.com",
    "meet.google.com",
}


def _normalize_meeting_url(url: str) -> str:
    """Collapse a meeting URL to a stable dedup key.

    Goal: two invitations to the same meeting must produce the same key, so a
    second join attempt by another participant is recognised as a duplicate.

    - Lowercase the host (case-insensitive per RFC 3986).
    - Drop the fragment.
    - For Teams / Meet, drop the entire query (`?context=`, `?p=`, etc. are
      session-specific and can vary across forwards of the same link).
    - For Zoom, drop the query too — `?pwd=` may be omitted on the second
      paste, and the meeting id lives in the path.

    Falls back to the trimmed input if the URL does not parse.
    """
    if not url:
        return ""
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return url.strip()
    if not parsed.netloc:
        return url.strip()

    host = parsed.netloc.lower()
    # Strip query for known meeting hosts and for any zoom.us subdomain.
    drop_query = host in _HOSTS_WITH_DISPOSABLE_QUERY or host.endswith(".zoom.us") or host == "zoom.us"
    return urlunparse((
        parsed.scheme.lower() or "https",
        host,
        parsed.path.rstrip("/"),
        "",  # params
        "" if drop_query else parsed.query,
        "",  # fragment — always dropped
    ))


class MeetingAlreadyJoinedError(Exception):
    """Raised when join_meeting is called for a meeting we already have an
    active bot in. Carries the existing bot id so the caller can surface a
    sensible message to the user."""

    def __init__(self, existing_bot_id: str, meeting_key: str):
        super().__init__(
            f"Bot {existing_bot_id} is already joined to meeting {meeting_key!r}"
        )
        self.existing_bot_id = existing_bot_id
        self.meeting_key = meeting_key


class RecallClient:
    """
    Recall.ai integration client.

    Flow:
    1. join_meeting() — sends a Recall bot to a meeting URL
    2. Recall bot records the meeting (video + audio)
    3. When done, Recall sends webhook to /api/recall/webhook
    4. get_video_url() — gets the video download URL
    5. We download and transcribe via OpenAI Whisper
    """

    BASE_URL = "https://eu-central-1.recall.ai/api/v1"

    def __init__(self):
        # In-memory mapping: recall_bot_id -> teams_conversation_id
        self._bot_conversations: dict[str, str] = {}
        # Active-meeting lock: normalized_url -> (bot_id, created_at_ts)
        # Used to dedupe join_meeting calls when several users paste the same
        # meeting link. Single-process only — fine because the bot runs in one
        # container; rebuild on restart is acceptable.
        self._active_meetings: dict[str, tuple[str, float]] = {}
        logger.info("RecallClient initialized")

    @property
    def is_configured(self) -> bool:
        return bool(settings.recall_api_key)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Token {settings.recall_api_key}",
            "Content-Type": "application/json",
        }

    async def join_meeting(
        self,
        meeting_url: str,
        teams_conversation_id: str,
        bot_name: str = None,
    ) -> dict:
        """Send a Recall bot to join a meeting.

        Raises `MeetingAlreadyJoinedError` if a bot we created is already in
        this meeting (within `MEETING_LOCK_TTL_SECONDS`). The caller must
        translate that into a user-facing message.
        """
        if not self.is_configured:
            raise ValueError("RECALL_API_KEY must be set in .env")

        meeting_key = _normalize_meeting_url(meeting_url)
        existing = self._active_meetings.get(meeting_key)
        if existing is not None:
            existing_bot_id, created_at = existing
            if time.time() - created_at < MEETING_LOCK_TTL_SECONDS:
                logger.info(
                    f"Skip join: bot {existing_bot_id} is already in meeting "
                    f"key={meeting_key!r}"
                )
                raise MeetingAlreadyJoinedError(
                    existing_bot_id=existing_bot_id, meeting_key=meeting_key
                )
            # Lock expired — drop it and fall through to a fresh join.
            logger.info(
                f"Meeting lock expired for key={meeting_key!r} "
                f"(bot={existing_bot_id}); allowing new join"
            )
            self._active_meetings.pop(meeting_key, None)

        bot_name = bot_name or settings.recall_bot_name

        payload = {
            "meeting_url": meeting_url,
            "bot_name": bot_name,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.BASE_URL}/bot/",
                json=payload,
                headers=self._headers(),
            )

            if response.status_code not in (200, 201):
                logger.error(f"Recall API error: {response.status_code} {response.text}")
                response.raise_for_status()

            data = response.json()

        recall_bot_id = data.get("id")
        logger.info(f"Recall bot created: id={recall_bot_id}, meeting={meeting_url}")

        if recall_bot_id:
            bot_id_str = str(recall_bot_id)
            self._bot_conversations[bot_id_str] = teams_conversation_id
            self._active_meetings[meeting_key] = (bot_id_str, time.time())
            logger.info(
                f"Mapped recall_bot={recall_bot_id} -> teams_conv={teams_conversation_id}, "
                f"meeting_key={meeting_key!r}"
            )

        return data

    def release_meeting_lock(self, bot_id: str) -> None:
        """Drop the active-meeting lock held by `bot_id`, if any.

        Called from the Recall webhook on terminal events (bot.done, fatal)
        so a follow-up meeting on the same URL is not blocked for 3 hours.
        Safe to call with an unknown bot_id (no-op).
        """
        bot_id_str = str(bot_id)
        for key, (existing_bot, _) in list(self._active_meetings.items()):
            if existing_bot == bot_id_str:
                del self._active_meetings[key]
                logger.info(f"Released meeting lock for bot {bot_id_str} (key={key!r})")
                return

    async def get_bot_status(self, bot_id: str) -> dict:
        """Get current status of a Recall bot"""
        if not self.is_configured:
            raise ValueError("RECALL_API_KEY must be set in .env")

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{self.BASE_URL}/bot/{bot_id}/",
                headers=self._headers(),
            )
            response.raise_for_status()
            return response.json()

    async def get_video_url(self, bot_id: str) -> Optional[str]:
        """Get the video download URL from a completed recording."""
        bot_data = await self.get_bot_status(bot_id)
        recordings = bot_data.get("recordings", [])
        if not recordings:
            return None

        video = recordings[0].get("media_shortcuts", {}).get("video_mixed", {})
        if video and video.get("status", {}).get("code") == "done":
            return video.get("data", {}).get("download_url")
        return None

    async def download_video(self, bot_id: str) -> Optional[str]:
        """
        Download video from Recall and save to temp file.
        Returns path to the downloaded mp4 file.
        """
        download_url = await self.get_video_url(bot_id)
        if not download_url:
            logger.error(f"No video URL for bot {bot_id}")
            return None

        # Download to temp file
        temp_dir = Path(tempfile.gettempdir()) / "recall_recordings"
        temp_dir.mkdir(exist_ok=True)
        temp_path = temp_dir / f"{bot_id}.mp4"

        logger.info(f"Downloading video for bot {bot_id}...")

        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.get(download_url)
            response.raise_for_status()

            with open(temp_path, "wb") as f:
                f.write(response.content)

        file_size = temp_path.stat().st_size / (1024 * 1024)
        logger.info(f"Video downloaded: {temp_path} ({file_size:.1f} MB)")
        return str(temp_path)

    async def get_transcript_by_id(self, transcript_id: str) -> list:
        """Download transcript by transcript ID from Recall EU API."""
        async with httpx.AsyncClient(timeout=60) as client:
            # Get transcript metadata (contains download_url)
            response = await client.get(
                f"{self.BASE_URL}/transcript/{transcript_id}/",
                headers=self._headers(),
            )
            response.raise_for_status()
            meta = response.json()

            download_url = meta.get("data", {}).get("download_url")
            if not download_url:
                logger.warning(f"No download_url for transcript {transcript_id}")
                return []

            # Download the actual transcript JSON
            transcript_response = await client.get(download_url)
            transcript_response.raise_for_status()
            segments = transcript_response.json()

            logger.info(f"Transcript downloaded for {transcript_id}: {len(segments)} segments")
            return segments

    async def get_speaker_timeline(self, bot_id: str) -> list:
        """
        Download speaker timeline from Recall.
        Returns list of entries: {participant: {name, id}, start_timestamp: {relative}, end_timestamp: {relative}}
        """
        bot_data = await self.get_bot_status(bot_id)
        recordings = bot_data.get("recordings", [])
        if not recordings:
            return []

        pe = recordings[0].get("media_shortcuts", {}).get("participant_events", {})
        stl_url = pe.get("data", {}).get("speaker_timeline_download_url")
        if not stl_url:
            logger.warning(f"No speaker_timeline URL for bot {bot_id}")
            return []

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(stl_url)
            response.raise_for_status()
            timeline = response.json()

        logger.info(f"Speaker timeline for bot {bot_id}: {len(timeline)} entries")
        return timeline

    def get_conversation_for_bot(self, bot_id: str) -> Optional[str]:
        """Get the Teams conversation ID associated with a Recall bot"""
        return self._bot_conversations.get(str(bot_id))

    def save_bot_conversation(self, bot_id: str, conversation_id: str):
        """Manually save a bot -> conversation mapping"""
        self._bot_conversations[str(bot_id)] = conversation_id
        logger.info(f"Mapped recall_bot={bot_id} -> teams_conv={conversation_id}")


# Singleton instance
recall_client = RecallClient()
