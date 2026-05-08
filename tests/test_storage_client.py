"""Tests for StorageClient — verified against a mocked supabase client.

Storage now hands back signed URLs (TTL via SUPABASE_SIGNED_URL_TTL_SECONDS),
not public URLs — so the bucket can be private. These tests pin that contract
by mocking `create_signed_url` on the bucket handle.
"""
from unittest.mock import MagicMock, patch

import pytest

from services.storage_client import StorageClient


def _make_client_with_mock(
    signed_url: str = "https://x.supabase.co/storage/v1/object/sign/meeting-protocols/bot-1/protocol.docx?token=abc",
):
    sc = StorageClient.__new__(StorageClient)
    mock_supabase = MagicMock()
    storage_from = mock_supabase.storage.from_.return_value
    storage_from.upload.return_value = MagicMock()
    storage_from.create_signed_url.return_value = {
        "signedURL": signed_url,
        "signedUrl": signed_url,
    }
    sc.client = mock_supabase
    return sc, mock_supabase, storage_from


@pytest.fixture
def fake_settings():
    with patch("services.storage_client.settings") as s:
        s.supabase_meetings_url = "https://x.supabase.co"
        s.supabase_meetings_service_key = "key"
        s.supabase_meetings_bucket = "meeting-protocols"
        s.supabase_signed_url_ttl_seconds = 60 * 60 * 24 * 30
        yield s


# --- Availability ---


def test_is_available_false_when_no_client():
    sc = StorageClient.__new__(StorageClient)
    sc.client = None
    assert sc.is_available is False


def test_upload_returns_none_when_unavailable(fake_settings):
    sc = StorageClient.__new__(StorageClient)
    sc.client = None
    assert sc.upload_meeting_artifact("bot-1", "protocol.docx", b"data") is None


# --- Happy path ---


def test_upload_uses_correct_path_and_returns_signed_url(fake_settings):
    expected_url = (
        "https://x.supabase.co/storage/v1/object/sign/"
        "meeting-protocols/bot-1/protocol.docx?token=abc"
    )
    sc, mock_supabase, storage_from = _make_client_with_mock(signed_url=expected_url)

    url = sc.upload_meeting_artifact(
        recall_bot_id="bot-1",
        filename="protocol.docx",
        content_bytes=b"docx-bytes",
    )
    assert url == expected_url

    mock_supabase.storage.from_.assert_called_with("meeting-protocols")
    upload_kwargs = storage_from.upload.call_args.kwargs
    assert upload_kwargs["path"] == "bot-1/protocol.docx"
    assert upload_kwargs["file"] == b"docx-bytes"
    assert upload_kwargs["file_options"]["content-type"].endswith("wordprocessingml.document")
    assert upload_kwargs["file_options"]["upsert"] == "true"

    storage_from.create_signed_url.assert_called_once_with(
        "bot-1/protocol.docx", 60 * 60 * 24 * 30
    )


def test_upload_uses_configured_bucket(fake_settings):
    fake_settings.supabase_meetings_bucket = "custom-bucket"
    sc, mock_supabase, storage_from = _make_client_with_mock()

    sc.upload_meeting_artifact("bot-1", "x.docx", b"d")
    mock_supabase.storage.from_.assert_called_with("custom-bucket")


def test_upload_passes_configured_ttl_to_create_signed_url(fake_settings):
    fake_settings.supabase_signed_url_ttl_seconds = 7 * 24 * 3600
    sc, _, storage_from = _make_client_with_mock()

    sc.upload_meeting_artifact("bot-1", "p.docx", b"d")
    storage_from.create_signed_url.assert_called_once_with(
        "bot-1/p.docx", 7 * 24 * 3600
    )


def test_upload_strips_trailing_question_mark(fake_settings):
    """Defensive: if a future supabase-py version returns a bare `...?`
    (empty query) we must not propagate the trailing `?` into Teams."""
    sc, _, _ = _make_client_with_mock(
        signed_url="https://x.supabase.co/storage/v1/object/sign/meeting-protocols/bot-1/p.docx?"
    )
    url = sc.upload_meeting_artifact("bot-1", "p.docx", b"d")
    assert url == (
        "https://x.supabase.co/storage/v1/object/sign/"
        "meeting-protocols/bot-1/p.docx"
    )


def test_upload_falls_back_to_signed_url_alias(fake_settings):
    """Some future supabase-py versions might drop the legacy `signedURL` key
    in favour of `signedUrl`. The client must accept either."""
    sc, _, storage_from = _make_client_with_mock()
    storage_from.create_signed_url.return_value = {
        "signedUrl": "https://x.supabase.co/storage/v1/object/sign/p.docx?t=zzz"
    }
    url = sc.upload_meeting_artifact("bot-1", "p.docx", b"d")
    assert url == "https://x.supabase.co/storage/v1/object/sign/p.docx?t=zzz"


# --- Failure modes ---


def test_upload_returns_none_on_upload_exception(fake_settings):
    sc, _, storage_from = _make_client_with_mock()
    storage_from.upload.side_effect = RuntimeError("Storage down")

    assert sc.upload_meeting_artifact("bot-1", "p.docx", b"d") is None


def test_upload_returns_none_on_create_signed_url_exception(fake_settings):
    sc, _, storage_from = _make_client_with_mock()
    storage_from.create_signed_url.side_effect = RuntimeError("Sign API down")

    assert sc.upload_meeting_artifact("bot-1", "p.docx", b"d") is None


def test_upload_returns_none_when_signed_response_is_empty(fake_settings):
    sc, _, storage_from = _make_client_with_mock()
    storage_from.create_signed_url.return_value = {}

    assert sc.upload_meeting_artifact("bot-1", "p.docx", b"d") is None


def test_upload_rejects_empty_args(fake_settings):
    sc, _, storage_from = _make_client_with_mock()

    assert sc.upload_meeting_artifact("", "p.docx", b"d") is None
    assert sc.upload_meeting_artifact("bot-1", "", b"d") is None
    storage_from.upload.assert_not_called()
    storage_from.create_signed_url.assert_not_called()
