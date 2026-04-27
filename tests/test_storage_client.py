"""Tests for StorageClient — verified against a mocked supabase client."""
from unittest.mock import MagicMock, patch

import pytest

from services.storage_client import StorageClient


def _make_client_with_mock(public_url: str = "https://x.supabase.co/storage/v1/object/public/meeting-protocols/bot-1/protocol.docx"):
    sc = StorageClient.__new__(StorageClient)
    mock_supabase = MagicMock()
    storage_from = mock_supabase.storage.from_.return_value
    storage_from.upload.return_value = MagicMock()
    storage_from.get_public_url.return_value = public_url
    sc.client = mock_supabase
    return sc, mock_supabase, storage_from


@pytest.fixture
def fake_settings():
    with patch("services.storage_client.settings") as s:
        s.supabase_meetings_url = "https://x.supabase.co"
        s.supabase_meetings_service_key = "key"
        s.supabase_meetings_bucket = "meeting-protocols"
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


def test_upload_uses_correct_path_and_returns_public_url(fake_settings):
    sc, mock_supabase, storage_from = _make_client_with_mock(
        public_url="https://x.supabase.co/storage/v1/object/public/meeting-protocols/bot-1/protocol.docx"
    )

    url = sc.upload_meeting_artifact(
        recall_bot_id="bot-1",
        filename="protocol.docx",
        content_bytes=b"docx-bytes",
    )
    assert url == "https://x.supabase.co/storage/v1/object/public/meeting-protocols/bot-1/protocol.docx"

    mock_supabase.storage.from_.assert_called_with("meeting-protocols")
    upload_kwargs = storage_from.upload.call_args.kwargs
    assert upload_kwargs["path"] == "bot-1/protocol.docx"
    assert upload_kwargs["file"] == b"docx-bytes"
    assert upload_kwargs["file_options"]["content-type"].endswith("wordprocessingml.document")
    assert upload_kwargs["file_options"]["upsert"] == "true"

    storage_from.get_public_url.assert_called_with("bot-1/protocol.docx")


def test_upload_uses_configured_bucket(fake_settings):
    fake_settings.supabase_meetings_bucket = "custom-bucket"
    sc, mock_supabase, storage_from = _make_client_with_mock()

    sc.upload_meeting_artifact("bot-1", "x.docx", b"d")
    mock_supabase.storage.from_.assert_called_with("custom-bucket")


# --- Failure modes ---


def test_upload_returns_none_on_exception(fake_settings):
    sc, mock_supabase, storage_from = _make_client_with_mock()
    storage_from.upload.side_effect = RuntimeError("Storage down")

    result = sc.upload_meeting_artifact("bot-1", "p.docx", b"d")
    assert result is None


def test_upload_rejects_empty_args(fake_settings):
    sc, _, storage_from = _make_client_with_mock()

    assert sc.upload_meeting_artifact("", "p.docx", b"d") is None
    assert sc.upload_meeting_artifact("bot-1", "", b"d") is None
    storage_from.upload.assert_not_called()
