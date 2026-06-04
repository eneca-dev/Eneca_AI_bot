"""Tests that RecallClient survives null-laden bot-status payloads.

get_video_url / get_speaker_timeline walk recordings[0].media_shortcuts.*.
Recall can return explicit nulls at any level. These must degrade to a
clean None / [] instead of raising 'NoneType' object has no attribute 'get'.
"""
from unittest.mock import patch, AsyncMock

import pytest

import services.recall_client as rc_module
from services.recall_client import RecallClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(rc_module.settings, "recall_api_key", "test-key")
    return RecallClient()


def _patch_status(client, bot_data):
    """Patch get_bot_status to return the given payload."""
    return patch.object(
        client, "get_bot_status", AsyncMock(return_value=bot_data)
    )


# --- get_video_url ---


@pytest.mark.asyncio
async def test_video_url_happy_path(client):
    bot_data = {
        "recordings": [
            {
                "media_shortcuts": {
                    "video_mixed": {
                        "status": {"code": "done"},
                        "data": {"download_url": "https://x/v.mp4"},
                    }
                }
            }
        ]
    }
    with _patch_status(client, bot_data):
        assert await client.get_video_url("b1") == "https://x/v.mp4"


@pytest.mark.asyncio
async def test_video_url_bot_data_none(client):
    with _patch_status(client, None):
        assert await client.get_video_url("b1") is None


@pytest.mark.asyncio
async def test_video_url_recordings_none(client):
    with _patch_status(client, {"recordings": None}):
        assert await client.get_video_url("b1") is None


@pytest.mark.asyncio
async def test_video_url_first_recording_none(client):
    with _patch_status(client, {"recordings": [None]}):
        assert await client.get_video_url("b1") is None


@pytest.mark.asyncio
async def test_video_url_media_shortcuts_none(client):
    with _patch_status(client, {"recordings": [{"media_shortcuts": None}]}):
        assert await client.get_video_url("b1") is None


@pytest.mark.asyncio
async def test_video_url_status_none(client):
    bot_data = {"recordings": [{"media_shortcuts": {"video_mixed": {"status": None}}}]}
    with _patch_status(client, bot_data):
        assert await client.get_video_url("b1") is None


@pytest.mark.asyncio
async def test_video_url_not_done(client):
    bot_data = {
        "recordings": [
            {"media_shortcuts": {"video_mixed": {"status": {"code": "processing"}}}}
        ]
    }
    with _patch_status(client, bot_data):
        assert await client.get_video_url("b1") is None


# --- get_speaker_timeline ---


@pytest.mark.asyncio
async def test_timeline_recordings_none(client):
    with _patch_status(client, {"recordings": None}):
        assert await client.get_speaker_timeline("b1") == []


@pytest.mark.asyncio
async def test_timeline_first_recording_none(client):
    with _patch_status(client, {"recordings": [None]}):
        assert await client.get_speaker_timeline("b1") == []


@pytest.mark.asyncio
async def test_timeline_media_shortcuts_none(client):
    with _patch_status(client, {"recordings": [{"media_shortcuts": None}]}):
        assert await client.get_speaker_timeline("b1") == []


@pytest.mark.asyncio
async def test_timeline_participant_events_none(client):
    bot_data = {"recordings": [{"media_shortcuts": {"participant_events": None}}]}
    with _patch_status(client, bot_data):
        assert await client.get_speaker_timeline("b1") == []


@pytest.mark.asyncio
async def test_timeline_no_url(client):
    bot_data = {
        "recordings": [{"media_shortcuts": {"participant_events": {"data": {}}}}]
    }
    with _patch_status(client, bot_data):
        assert await client.get_speaker_timeline("b1") == []


@pytest.mark.asyncio
async def test_timeline_happy_path(client):
    bot_data = {
        "recordings": [
            {
                "media_shortcuts": {
                    "participant_events": {
                        "data": {"speaker_timeline_download_url": "https://x/t.json"}
                    }
                }
            }
        ]
    }
    fake_resp = AsyncMock()
    fake_resp.json = lambda: [{"participant": {"name": "Иван"}}]
    fake_resp.raise_for_status = lambda: None

    with _patch_status(client, bot_data), \
            patch("services.recall_client.httpx.AsyncClient") as mock_client:
        get_mock = AsyncMock(return_value=fake_resp)
        mock_client.return_value.__aenter__.return_value.get = get_mock
        result = await client.get_speaker_timeline("b1")

    assert result == [{"participant": {"name": "Иван"}}]
