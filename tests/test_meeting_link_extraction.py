"""Tests for meeting URL extraction.

Covers two layers:
- `extract_meeting_url(text)` — legacy plain-text + href extraction (regression).
- `extract_meeting_url_from_activity(activity)` — full Bot Framework payload
  walk, the new behaviour added to fix link-as-label cases.
"""
import pytest

from server import extract_meeting_url, extract_meeting_url_from_activity


# --- Plain text and href (regression of legacy extract_meeting_url) ---


def test_extracts_plain_https_url():
    text = "Привет! https://teams.microsoft.com/meet/123456789?p=abc хорошая встреча"
    assert (
        extract_meeting_url(text)
        == "https://teams.microsoft.com/meet/123456789?p=abc"
    )


def test_extracts_url_from_href_attribute():
    text = '<a href="https://teams.microsoft.com/meet/987654321?p=xyz">Созвон</a>'
    assert (
        extract_meeting_url(text)
        == "https://teams.microsoft.com/meet/987654321?p=xyz"
    )


def test_strips_trailing_punctuation():
    text = "присоединяйся: https://teams.microsoft.com/meet/123!"
    assert extract_meeting_url(text) == "https://teams.microsoft.com/meet/123"


def test_returns_none_for_empty_text():
    assert extract_meeting_url("") is None
    assert extract_meeting_url(None) is None


def test_ignores_non_meeting_urls():
    text = "https://youtube.com/watch?v=abc и https://example.com"
    assert extract_meeting_url(text) is None


def test_picks_first_meeting_url_when_multiple():
    text = (
        "https://teams.microsoft.com/meet/AAA "
        "и https://teams.microsoft.com/meet/BBB"
    )
    assert extract_meeting_url(text) == "https://teams.microsoft.com/meet/AAA"


# --- Full activity walk (the link-as-label fix) ---


def test_activity_with_url_in_plain_text():
    activity = {
        "type": "message",
        "text": "https://teams.microsoft.com/meet/123",
    }
    assert (
        extract_meeting_url_from_activity(activity)
        == "https://teams.microsoft.com/meet/123"
    )


def test_activity_with_label_only_text_and_url_in_attachment_tap_value():
    """The exact case from the bug report: user pastes a link with anchor
    text, Teams keeps the URL only in `attachments[*].content.tap.value`."""
    activity = {
        "type": "message",
        "text": "Созвон с Артемом | Meeting-Join | Microsoft Teams",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.hero",
                "content": {
                    "title": "Присоединиться к собранию в Teams",
                    "tap": {
                        "type": "openUrl",
                        "value": "https://teams.microsoft.com/meet/393739051305077?p=ILill1YprBKEl8Gizx",
                    },
                },
            }
        ],
    }
    assert (
        extract_meeting_url_from_activity(activity)
        == "https://teams.microsoft.com/meet/393739051305077?p=ILill1YprBKEl8Gizx"
    )


def test_activity_with_url_in_attachment_button_value():
    activity = {
        "type": "message",
        "text": "Зайди в созвон",
        "attachments": [
            {
                "content": {
                    "buttons": [
                        {
                            "type": "openUrl",
                            "value": "https://teams.microsoft.com/meet/777",
                        },
                    ],
                },
            }
        ],
    }
    assert (
        extract_meeting_url_from_activity(activity)
        == "https://teams.microsoft.com/meet/777"
    )


def test_activity_with_url_deep_in_adaptive_card_body():
    activity = {
        "type": "message",
        "text": "Созвон",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "body": [
                        {"type": "TextBlock", "text": "присоединяйся:"},
                        {
                            "type": "TextBlock",
                            "text": "https://teams.microsoft.com/meet/deep-id",
                        },
                    ],
                },
            }
        ],
    }
    assert (
        extract_meeting_url_from_activity(activity)
        == "https://teams.microsoft.com/meet/deep-id"
    )


def test_activity_without_text_field_does_not_crash():
    activity = {
        "type": "message",
        "attachments": [
            {
                "content": {
                    "tap": {"value": "https://teams.microsoft.com/meet/no-text"},
                },
            }
        ],
    }
    assert (
        extract_meeting_url_from_activity(activity)
        == "https://teams.microsoft.com/meet/no-text"
    )


def test_activity_with_no_meeting_link_anywhere_returns_none():
    activity = {
        "type": "message",
        "text": "Привет, как дела?",
        "attachments": [
            {"content": {"text": "просто карточка без ссылки"}},
        ],
    }
    assert extract_meeting_url_from_activity(activity) is None


def test_empty_or_none_activity_returns_none():
    assert extract_meeting_url_from_activity({}) is None
    assert extract_meeting_url_from_activity(None) is None


def test_extracts_zoom_url_from_attachment():
    activity = {
        "type": "message",
        "text": "Zoom-созвон",
        "attachments": [
            {
                "content": {
                    "tap": {"value": "https://us05web.zoom.us/j/12345?pwd=secret"},
                },
            }
        ],
    }
    assert (
        extract_meeting_url_from_activity(activity)
        == "https://us05web.zoom.us/j/12345?pwd=secret"
    )


def test_extracts_meet_url_from_attachment():
    activity = {
        "type": "message",
        "text": "Подключение",
        "attachments": [
            {
                "content": {
                    "buttons": [
                        {"value": "https://meet.google.com/abc-defg-hij"},
                    ],
                },
            }
        ],
    }
    assert (
        extract_meeting_url_from_activity(activity)
        == "https://meet.google.com/abc-defg-hij"
    )


def test_label_text_alone_does_not_match():
    """Without the attachment, the label `Meeting-Join | Microsoft Teams` must
    NOT be misread as a URL. This is the original bug — verify it's still a
    'no-match' when only the label is present."""
    activity = {
        "type": "message",
        "text": "Созвон с Артемом | Meeting-Join | Microsoft Teams",
    }
    assert extract_meeting_url_from_activity(activity) is None


# --- bug-VN-01: Zoom host must respect a subdomain boundary ---


@pytest.mark.parametrize(
    "url",
    [
        "https://zoom.us/j/123456",
        "https://us02web.zoom.us/j/85512345678?pwd=Qm5k",
        "https://acme.zoom.us/j/123456",       # vanity / corporate subdomain
        "https://us02web.zoom.us/w/123456",    # webinar path
    ],
)
def test_zoom_real_domains_match(url):
    assert extract_meeting_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "https://evilzoom.us/j/123456",        # lookalike glued onto `zoom`
        "https://x.evilzoom.us/j/123456",      # lookalike with a subdomain
        "https://zoom.us.evil.com/j/123456",   # `zoom.us` as a fake subdomain
    ],
)
def test_zoom_lookalike_domains_do_not_match(url):
    """bug-VN-01: `[\\w.-]*zoom\\.us` used to match any host ending in
    `zoom.us` (e.g. `evilzoom.us`). The subdomain-boundary pattern rejects them."""
    assert extract_meeting_url(url) is None
    assert extract_meeting_url_from_activity({"type": "message", "text": url}) is None
