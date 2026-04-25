"""Tests for MeetingsDBClient — verified against a mocked Supabase client.

We don't hit real Supabase. The goal is to verify row shape and the
correct branch selection for each method.
"""
from unittest.mock import MagicMock

import pytest

from database import meetings_client as mc_module
from database.meetings_client import (
    MeetingsDBClient, TABLE,
    STATUS_PROCESSING, STATUS_DONE, STATUS_ERROR,
)


# --- Helpers ---


def _make_client_with_mock(insert_response=None, update_response=None, select_response=None,
                           upsert_response=None, insert_raises=None):
    """Construct a MeetingsDBClient with its Supabase client replaced by a mock.

    Each `*_response` argument is the `data` list the corresponding builder returns.
    `insert_raises` lets us simulate a unique-constraint violation on INSERT.
    """
    client = MeetingsDBClient.__new__(MeetingsDBClient)  # skip __init__ (no real Supabase)
    mock_supabase = MagicMock()
    table_mock = mock_supabase.table.return_value

    def _resp(data):
        r = MagicMock()
        r.data = data if data is not None else [{"id": "abc-123"}]
        return r

    insert_resp = _resp(insert_response)
    if insert_raises is not None:
        table_mock.insert.return_value.execute.side_effect = insert_raises
    else:
        table_mock.insert.return_value.execute.return_value = insert_resp

    table_mock.update.return_value.eq.return_value.execute.return_value = _resp(update_response)
    table_mock.upsert.return_value.execute.return_value = _resp(upsert_response)
    table_mock.select.return_value.eq.return_value.limit.return_value.execute.return_value = _resp(select_response)

    client.client = mock_supabase
    return client, mock_supabase, table_mock


def _sample_report_dict():
    return {
        "subject": "Sync",
        "date": "2026-04-25",
        "duration": None,
        "project": None,
        "participants": [{"name": "Иван", "organization": None, "role": None}],
        "preview_summary": None,
        "discussion_items": [],
        "open_questions": [],
        "risks": [],
        "location": "Microsoft Teams",
        "transcript_url": None,
        "previous_protocol_url": None,
        "author": {"organization": "Eneca", "name": "Meeting Bot", "role": "Автоматический протокол"},
    }


def _sample_transcript_dict():
    return {
        "title": "Sync",
        "date": "2026-04-25",
        "duration": None,
        "participants": [{"name": "Иван", "organization": None, "role": None}],
        "transcript": [{"speaker": "Иван", "timestamp": "00:01", "text": "Привет"}],
    }


# --- Availability ---


def test_is_available_false_when_no_client():
    client = MeetingsDBClient.__new__(MeetingsDBClient)
    client.client = None
    assert client.is_available() is False


# --- start_meeting_processing ---


def test_start_meeting_processing_inserts_row_with_processing_status():
    client, _, table_mock = _make_client_with_mock(insert_response=[{"id": "row-1"}])
    result = client.start_meeting_processing(
        recall_bot_id="bot-1", subject="Sync", meeting_date="2026-04-25",
    )
    assert result == {"id": "row-1"}
    table_mock.insert.assert_called_once()
    row = table_mock.insert.call_args[0][0]
    assert row == {
        "recall_bot_id": "bot-1",
        "status": STATUS_PROCESSING,
        "subject": "Sync",
        "meeting_date": "2026-04-25",
    }


def test_start_meeting_processing_with_minimal_args():
    client, _, table_mock = _make_client_with_mock(insert_response=[{"id": "row-1"}])
    client.start_meeting_processing(recall_bot_id="bot-1")
    row = table_mock.insert.call_args[0][0]
    assert row["subject"] is None
    assert row["meeting_date"] is None
    assert row["status"] == STATUS_PROCESSING


def test_start_meeting_processing_handles_duplicate_via_select_fallback():
    """A unique-constraint failure (webhook retry) must not raise — fall back to fetching the existing row."""
    existing = {"id": "row-1", "status": "done", "recall_bot_id": "bot-1"}
    client, _, table_mock = _make_client_with_mock(
        insert_raises=Exception("duplicate key value violates unique constraint"),
        select_response=[existing],
    )
    result = client.start_meeting_processing(recall_bot_id="bot-1")
    assert result == existing


def test_start_meeting_processing_returns_none_when_unavailable():
    client = MeetingsDBClient.__new__(MeetingsDBClient)
    client.client = None
    assert client.start_meeting_processing("bot-1") is None


# --- complete_meeting_report ---


def test_complete_meeting_report_updates_existing_row():
    client, _, table_mock = _make_client_with_mock(update_response=[{"id": "row-1"}])
    result = client.complete_meeting_report(
        recall_bot_id="bot-1",
        report=_sample_report_dict(),
        transcript=_sample_transcript_dict(),
    )
    assert result == {"id": "row-1"}
    table_mock.update.assert_called_once()
    update_row = table_mock.update.call_args[0][0]
    assert update_row["status"] == STATUS_DONE
    assert update_row["subject"] == "Sync"
    assert update_row["meeting_date"] == "2026-04-25"
    assert update_row["report"] == _sample_report_dict()
    assert update_row["transcript"] == _sample_transcript_dict()
    assert update_row["error_message"] is None
    table_mock.update.return_value.eq.assert_called_with("recall_bot_id", "bot-1")


def test_complete_meeting_report_falls_back_to_upsert_when_no_row():
    """If start_meeting_processing was missed, complete should still persist via upsert."""
    client, _, table_mock = _make_client_with_mock(
        update_response=[],            # UPDATE matched nothing
        upsert_response=[{"id": "row-X", "status": "done"}],
    )
    result = client.complete_meeting_report(
        recall_bot_id="bot-1",
        report=_sample_report_dict(),
        transcript=_sample_transcript_dict(),
    )
    assert result == {"id": "row-X", "status": "done"}
    table_mock.upsert.assert_called_once()


def test_complete_meeting_report_returns_none_on_exception():
    client, _, table_mock = _make_client_with_mock()
    table_mock.update.return_value.eq.return_value.execute.side_effect = RuntimeError("DB down")
    result = client.complete_meeting_report(
        recall_bot_id="bot-1",
        report=_sample_report_dict(),
        transcript=None,
    )
    assert result is None


# --- mark_meeting_error ---


def test_mark_meeting_error_updates_existing_row():
    client, _, table_mock = _make_client_with_mock(update_response=[{"id": "row-1"}])
    result = client.mark_meeting_error("bot-1", "Whisper failed")
    assert result == {"id": "row-1"}
    update_row = table_mock.update.call_args[0][0]
    assert update_row == {"status": STATUS_ERROR, "error_message": "Whisper failed"}


def test_mark_meeting_error_truncates_long_messages():
    long_msg = "x" * 5000
    client, _, table_mock = _make_client_with_mock(update_response=[{"id": "row-1"}])
    client.mark_meeting_error("bot-1", long_msg)
    update_row = table_mock.update.call_args[0][0]
    assert len(update_row["error_message"]) == 2000


def test_mark_meeting_error_inserts_when_no_row_to_update():
    client, _, table_mock = _make_client_with_mock(
        update_response=[],
        insert_response=[{"id": "row-Y", "status": "error"}],
    )
    result = client.mark_meeting_error("bot-1", "boom")
    assert result == {"id": "row-Y", "status": "error"}
    table_mock.insert.assert_called_once()
    insert_row = table_mock.insert.call_args[0][0]
    assert insert_row == {
        "recall_bot_id": "bot-1",
        "status": STATUS_ERROR,
        "error_message": "boom",
    }


# --- upsert_meeting_report (sync flow) ---


def test_upsert_with_bot_id_uses_upsert_on_conflict():
    client, mock_supabase, table_mock = _make_client_with_mock(upsert_response=[{"id": "abc-1"}])
    result = client.upsert_meeting_report(
        report=_sample_report_dict(),
        transcript=_sample_transcript_dict(),
        recall_bot_id="bot-42",
    )
    mock_supabase.table.assert_called_with(TABLE)
    args, kwargs = table_mock.upsert.call_args
    row = args[0]
    assert kwargs == {"on_conflict": "recall_bot_id"}
    assert row["recall_bot_id"] == "bot-42"
    assert row["status"] == STATUS_DONE
    assert row["subject"] == "Sync"
    assert row["meeting_date"] == "2026-04-25"
    assert row["report"] == _sample_report_dict()
    assert result == {"id": "abc-1"}


def test_upsert_without_bot_id_uses_plain_insert():
    client, _, table_mock = _make_client_with_mock(insert_response=[{"id": "abc"}])
    client.upsert_meeting_report(
        report=_sample_report_dict(),
        transcript=_sample_transcript_dict(),
        recall_bot_id=None,
    )
    table_mock.insert.assert_called_once()
    table_mock.upsert.assert_not_called()
    args, _ = table_mock.insert.call_args
    assert args[0]["recall_bot_id"] is None
    assert args[0]["status"] == STATUS_DONE


def test_upsert_accepts_explicit_status():
    client, _, table_mock = _make_client_with_mock(insert_response=[{"id": "abc"}])
    client.upsert_meeting_report(
        report=_sample_report_dict(),
        recall_bot_id=None,
        status=STATUS_ERROR,
    )
    args, _ = table_mock.insert.call_args
    assert args[0]["status"] == STATUS_ERROR


def test_upsert_returns_none_on_exception():
    client, _, table_mock = _make_client_with_mock()
    table_mock.insert.return_value.execute.side_effect = RuntimeError("DB down")
    result = client.upsert_meeting_report(
        report=_sample_report_dict(),
        transcript=None,
        recall_bot_id=None,
    )
    assert result is None


def test_upsert_row_contains_only_schema_columns():
    client, _, table_mock = _make_client_with_mock(upsert_response=[{"id": "abc"}])
    client.upsert_meeting_report(
        report=_sample_report_dict(),
        transcript=_sample_transcript_dict(),
        recall_bot_id="bot-1",
    )
    row = table_mock.upsert.call_args[0][0]
    assert set(row.keys()) == {"recall_bot_id", "status", "subject", "meeting_date", "report", "transcript"}


# --- Read ---


def test_get_by_bot_id_returns_first_row():
    client, _, table_mock = _make_client_with_mock(select_response=[{"id": "x", "subject": "S"}])
    result = client.get_meeting_report_by_bot_id("bot-1")
    assert result == {"id": "x", "subject": "S"}


def test_get_by_bot_id_returns_none_when_empty():
    client, _, table_mock = _make_client_with_mock(select_response=[])
    result = client.get_meeting_report_by_bot_id("bot-1")
    assert result is None


# --- Module ---


def test_module_singleton_exists():
    assert hasattr(mc_module, "meetings_db_client")
    assert isinstance(mc_module.meetings_db_client, MeetingsDBClient)


def test_status_constants_match_check_constraint():
    assert STATUS_PROCESSING == "processing"
    assert STATUS_DONE == "done"
    assert STATUS_ERROR == "error"
