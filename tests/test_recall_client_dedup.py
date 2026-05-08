"""Tests for the in-memory dedup added to RecallClient.

Two layers:
- `_normalize_meeting_url`: pure URL → key reduction.
- `RecallClient.join_meeting`: dedup contract — second call for the same
  meeting raises `MeetingAlreadyJoinedError` instead of creating a new bot.
"""
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

import services.recall_client as rc_module
from services.recall_client import (
    MeetingAlreadyJoinedError,
    MEETING_LOCK_TTL_SECONDS,
    RecallClient,
    _normalize_meeting_url,
)


# --- _normalize_meeting_url ---


def test_normalize_teams_strips_context_query():
    a = _normalize_meeting_url(
        "https://teams.microsoft.com/meet/123?context=abc&p=xyz"
    )
    b = _normalize_meeting_url("https://teams.microsoft.com/meet/123")
    assert a == b == "https://teams.microsoft.com/meet/123"


def test_normalize_teams_meetup_join_preserves_path():
    raw = (
        "https://teams.microsoft.com/l/meetup-join/"
        "19%3ameeting_abc%40thread.v2/0?context=%7b%22Tid%22%3a%22xyz%22%7d"
    )
    norm = _normalize_meeting_url(raw)
    assert norm == (
        "https://teams.microsoft.com/l/meetup-join/"
        "19%3ameeting_abc%40thread.v2/0"
    )


def test_normalize_zoom_strips_pwd_keeps_id():
    a = _normalize_meeting_url("https://us05web.zoom.us/j/12345?pwd=secret")
    b = _normalize_meeting_url("https://us05web.zoom.us/j/12345")
    assert a == b == "https://us05web.zoom.us/j/12345"


def test_normalize_meet_drops_query():
    a = _normalize_meeting_url(
        "https://meet.google.com/abc-defg-hij?authuser=0"
    )
    b = _normalize_meeting_url("https://meet.google.com/abc-defg-hij")
    assert a == b == "https://meet.google.com/abc-defg-hij"


def test_normalize_lowercases_host():
    norm = _normalize_meeting_url("https://Teams.Microsoft.COM/meet/123")
    assert norm == "https://teams.microsoft.com/meet/123"


def test_normalize_drops_fragment():
    norm = _normalize_meeting_url("https://teams.microsoft.com/meet/123#part")
    assert norm == "https://teams.microsoft.com/meet/123"


def test_normalize_strips_trailing_slash():
    a = _normalize_meeting_url("https://teams.microsoft.com/meet/123/")
    b = _normalize_meeting_url("https://teams.microsoft.com/meet/123")
    assert a == b


def test_normalize_is_idempotent():
    raw = "https://teams.microsoft.com/meet/123?context=abc#frag"
    once = _normalize_meeting_url(raw)
    twice = _normalize_meeting_url(once)
    assert once == twice


def test_normalize_empty_input_returns_empty():
    assert _normalize_meeting_url("") == ""
    assert _normalize_meeting_url(None) == ""


# --- RecallClient.join_meeting dedup ---


@pytest.fixture
def client_with_api_key(monkeypatch):
    """Fresh RecallClient with API key configured."""
    monkeypatch.setattr(rc_module.settings, "recall_api_key", "test-key")
    monkeypatch.setattr(rc_module.settings, "recall_bot_name", "TestBot")
    return RecallClient()


def _mock_post_returning(bot_id: str):
    """Build a side_effect for httpx.AsyncClient.post that returns a fake bot."""
    response = MagicMock()
    response.status_code = 201
    response.json.return_value = {"id": bot_id}
    response.raise_for_status = MagicMock()
    return AsyncMock(return_value=response)


@pytest.mark.asyncio
async def test_first_join_creates_bot_and_records_lock(client_with_api_key):
    post_mock = _mock_post_returning("bot-1")
    with patch("services.recall_client.httpx.AsyncClient") as mock_async_client:
        mock_async_client.return_value.__aenter__.return_value.post = post_mock
        result = await client_with_api_key.join_meeting(
            "https://teams.microsoft.com/meet/aaa?context=foo",
            teams_conversation_id="conv-1",
        )

    assert result == {"id": "bot-1"}
    post_mock.assert_called_once()
    # Lock recorded under the normalized key, not the raw URL.
    assert (
        "https://teams.microsoft.com/meet/aaa"
        in client_with_api_key._active_meetings
    )


@pytest.mark.asyncio
async def test_second_join_same_meeting_raises_without_calling_recall(
    client_with_api_key,
):
    post_mock = _mock_post_returning("bot-1")
    with patch("services.recall_client.httpx.AsyncClient") as mock_async_client:
        mock_async_client.return_value.__aenter__.return_value.post = post_mock

        await client_with_api_key.join_meeting(
            "https://teams.microsoft.com/meet/aaa?context=first",
            teams_conversation_id="conv-1",
        )

        # Second call — different query, same canonical meeting.
        with pytest.raises(MeetingAlreadyJoinedError) as exc:
            await client_with_api_key.join_meeting(
                "https://teams.microsoft.com/meet/aaa?context=second",
                teams_conversation_id="conv-2",
            )

    assert exc.value.existing_bot_id == "bot-1"
    assert exc.value.meeting_key == "https://teams.microsoft.com/meet/aaa"
    # Only the FIRST join made an HTTP call.
    assert post_mock.call_count == 1


@pytest.mark.asyncio
async def test_different_meetings_do_not_interfere(client_with_api_key):
    post_mock = AsyncMock(side_effect=[
        MagicMock(status_code=201, json=lambda: {"id": "bot-1"}, raise_for_status=MagicMock()),
        MagicMock(status_code=201, json=lambda: {"id": "bot-2"}, raise_for_status=MagicMock()),
    ])
    with patch("services.recall_client.httpx.AsyncClient") as mock_async_client:
        mock_async_client.return_value.__aenter__.return_value.post = post_mock

        await client_with_api_key.join_meeting(
            "https://teams.microsoft.com/meet/aaa",
            teams_conversation_id="conv-1",
        )
        result_b = await client_with_api_key.join_meeting(
            "https://teams.microsoft.com/meet/bbb",
            teams_conversation_id="conv-2",
        )

    assert result_b == {"id": "bot-2"}
    assert post_mock.call_count == 2
    assert len(client_with_api_key._active_meetings) == 2


@pytest.mark.asyncio
async def test_release_meeting_lock_allows_new_join(client_with_api_key):
    post_mock = AsyncMock(side_effect=[
        MagicMock(status_code=201, json=lambda: {"id": "bot-1"}, raise_for_status=MagicMock()),
        MagicMock(status_code=201, json=lambda: {"id": "bot-2"}, raise_for_status=MagicMock()),
    ])
    with patch("services.recall_client.httpx.AsyncClient") as mock_async_client:
        mock_async_client.return_value.__aenter__.return_value.post = post_mock

        await client_with_api_key.join_meeting(
            "https://teams.microsoft.com/meet/aaa",
            teams_conversation_id="conv-1",
        )
        client_with_api_key.release_meeting_lock("bot-1")
        # Now a fresh join should hit Recall again, not raise.
        result = await client_with_api_key.join_meeting(
            "https://teams.microsoft.com/meet/aaa",
            teams_conversation_id="conv-1",
        )

    assert result == {"id": "bot-2"}
    assert post_mock.call_count == 2


@pytest.mark.asyncio
async def test_lock_expires_after_ttl(client_with_api_key):
    post_mock = AsyncMock(side_effect=[
        MagicMock(status_code=201, json=lambda: {"id": "bot-1"}, raise_for_status=MagicMock()),
        MagicMock(status_code=201, json=lambda: {"id": "bot-2"}, raise_for_status=MagicMock()),
    ])
    fake_now = [1_000_000.0]

    def _time():
        return fake_now[0]

    with patch("services.recall_client.httpx.AsyncClient") as mock_async_client, \
            patch("services.recall_client.time.time", side_effect=_time):
        mock_async_client.return_value.__aenter__.return_value.post = post_mock

        await client_with_api_key.join_meeting(
            "https://teams.microsoft.com/meet/aaa",
            teams_conversation_id="conv-1",
        )
        # Jump past TTL — second join is allowed.
        fake_now[0] += MEETING_LOCK_TTL_SECONDS + 1
        result = await client_with_api_key.join_meeting(
            "https://teams.microsoft.com/meet/aaa",
            teams_conversation_id="conv-1",
        )

    assert result == {"id": "bot-2"}
    assert post_mock.call_count == 2


def test_release_unknown_bot_id_is_noop(client_with_api_key):
    # Should not raise even if we never tracked this bot.
    client_with_api_key.release_meeting_lock("never-seen")
    assert client_with_api_key._active_meetings == {}


@pytest.mark.asyncio
async def test_join_without_api_key_raises(monkeypatch):
    monkeypatch.setattr(rc_module.settings, "recall_api_key", None)
    client = RecallClient()
    with pytest.raises(ValueError):
        await client.join_meeting(
            "https://teams.microsoft.com/meet/aaa",
            teams_conversation_id="conv-1",
        )
