"""Regression tests for bug-VN-03: _process_recording_with_whisper must not
re-run the (expensive) Whisper+LLM pipeline for a recording that is already
'done' — a delayed duplicate Recall webhook delivery should be a no-op.

A row in 'processing'/'error' is NOT skipped: that may be a stuck or failed
prior run that legitimately needs a retry.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import server


def _patches(start_status: str):
    """Build mocks for the dependencies _process_recording touches before/at the guard."""
    rc = MagicMock()
    rc.get_conversation_for_bot.return_value = None      # no Teams notify path
    rc.get_inviter_for_bot.return_value = {}
    rc.get_bot_status = AsyncMock(return_value={})        # early metadata fetch
    rc.download_video = AsyncMock(return_value=None)      # if reached → ValueError (caught)

    gc = MagicMock()
    gc.get_user_email = AsyncMock(return_value=None)

    db = MagicMock()
    db.start_meeting_processing.return_value = {"status": start_status}

    return rc, gc, db


@pytest.mark.asyncio
async def test_skips_processing_when_row_already_done():
    rc, gc, db = _patches(start_status="done")
    with patch("server.recall_client", rc), \
         patch("server.graph_client", gc), \
         patch("server.meetings_db_client", db):
        await server._process_recording_with_whisper("bot-dup")

    # Guard must short-circuit BEFORE downloading / transcribing.
    rc.download_video.assert_not_called()


@pytest.mark.asyncio
async def test_processes_when_row_is_processing():
    """Not 'done' → no skip: the worker proceeds (download is attempted)."""
    rc, gc, db = _patches(start_status="processing")
    with patch("server.recall_client", rc), \
         patch("server.graph_client", gc), \
         patch("server.meetings_db_client", db):
        await server._process_recording_with_whisper("bot-new")

    # Proceeded past the guard → tried to download (returns None → handled internally).
    rc.download_video.assert_called_once()
