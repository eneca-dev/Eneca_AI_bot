"""Tests for None-safe extraction of Recall API payloads.

Regression for the production crash:
    'NoneType' object has no attribute 'get'

Recall's bot-status JSON can carry explicit `null` at any nesting level
(key present, value None). A plain `.get(a, {}).get(b, {})` chain does NOT
apply the `{}` default in that case — it returns the None and the next
`.get` raises AttributeError. These helpers must survive every shape:
missing key, explicit null, empty list, and a list whose first item is null.
"""
import pytest

from server import (
    _extract_meeting_metadata,
    _participant_name,
    _ts_relative,
)


# --- _extract_meeting_metadata ---


def test_metadata_happy_path():
    bot_data = {
        "recordings": [
            {"media_shortcuts": {"meeting_metadata": {"data": {"title": "Sync"}}}}
        ]
    }
    assert _extract_meeting_metadata(bot_data) == {"title": "Sync"}


def test_metadata_none_bot_data():
    assert _extract_meeting_metadata(None) == {}


def test_metadata_no_recordings_key():
    assert _extract_meeting_metadata({}) == {}


def test_metadata_recordings_is_none():
    # Key present, value explicitly null — the bug case.
    assert _extract_meeting_metadata({"recordings": None}) == {}


def test_metadata_recordings_empty_list():
    assert _extract_meeting_metadata({"recordings": []}) == {}


def test_metadata_first_recording_is_none():
    assert _extract_meeting_metadata({"recordings": [None]}) == {}


def test_metadata_media_shortcuts_is_none():
    bot_data = {"recordings": [{"media_shortcuts": None}]}
    assert _extract_meeting_metadata(bot_data) == {}


def test_metadata_meeting_metadata_is_none():
    bot_data = {"recordings": [{"media_shortcuts": {"meeting_metadata": None}}]}
    assert _extract_meeting_metadata(bot_data) == {}


def test_metadata_data_is_none():
    bot_data = {
        "recordings": [{"media_shortcuts": {"meeting_metadata": {"data": None}}}]
    }
    assert _extract_meeting_metadata(bot_data) == {}


# --- _participant_name ---


def test_participant_name_happy_path():
    assert _participant_name({"participant": {"name": "Иван"}}) == "Иван"


def test_participant_name_entry_none():
    assert _participant_name(None) == "Speaker"


def test_participant_name_participant_none():
    # The exact null shape that crashed: {"participant": None}.
    assert _participant_name({"participant": None}) == "Speaker"


def test_participant_name_missing_name():
    assert _participant_name({"participant": {}}) == "Speaker"


def test_participant_name_name_is_none():
    assert _participant_name({"participant": {"name": None}}) == "Speaker"


def test_participant_name_custom_default():
    assert _participant_name(None, "?") == "?"


# --- _ts_relative ---


def test_ts_relative_happy_path():
    assert _ts_relative({"start_timestamp": {"relative": 12.5}}, "start_timestamp") == 12.5


def test_ts_relative_entry_none():
    assert _ts_relative(None, "start_timestamp") == 0


def test_ts_relative_timestamp_none():
    assert _ts_relative({"start_timestamp": None}, "start_timestamp") == 0


def test_ts_relative_missing_key():
    assert _ts_relative({}, "end_timestamp") == 0


def test_ts_relative_relative_none():
    assert _ts_relative({"end_timestamp": {"relative": None}}, "end_timestamp") == 0
