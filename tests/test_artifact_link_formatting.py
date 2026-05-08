"""Tests for the DOCX-artifact link formatter used in the Recall webhook flow.

Verifies the markdown shape sent to Teams: `[label](url)` so the Teams
renderer never attaches trailing punctuation to the URL or breaks the link
on parentheses inside the label.
"""
from server import _format_artifact_links


def test_returns_empty_string_when_no_urls():
    assert _format_artifact_links({}) == ""
    assert _format_artifact_links({
        "protocol_docx_url": None,
        "transcript_docx_url": None,
    }) == ""


def test_renders_only_protocol_when_transcript_missing():
    out = _format_artifact_links({
        "protocol_docx_url": "https://x.supabase.co/p.docx?token=a",
        "transcript_docx_url": None,
    })
    assert out == "[📄 Протокол DOCX](https://x.supabase.co/p.docx?token=a)"


def test_renders_only_transcript_when_protocol_missing():
    out = _format_artifact_links({
        "protocol_docx_url": None,
        "transcript_docx_url": "https://x.supabase.co/t.docx?token=b",
    })
    assert out == "[📝 Транскрипт DOCX](https://x.supabase.co/t.docx?token=b)"


def test_renders_both_links_in_order_protocol_then_transcript():
    out = _format_artifact_links({
        "protocol_docx_url": "https://x.supabase.co/p.docx?token=a",
        "transcript_docx_url": "https://x.supabase.co/t.docx?token=b",
    })
    assert out == (
        "[📄 Протокол DOCX](https://x.supabase.co/p.docx?token=a)\n"
        "[📝 Транскрипт DOCX](https://x.supabase.co/t.docx?token=b)"
    )


def test_label_contains_no_parentheses_so_it_does_not_break_markdown_parser():
    """Teams renders [label](url). If `label` itself contains `)`, naive
    parsers can close the link prematurely. Our labels must be paren-free."""
    out = _format_artifact_links({
        "protocol_docx_url": "https://x/p?t=a",
        "transcript_docx_url": "https://x/t?t=b",
    })
    # extract the label portion of each markdown link
    labels = [line.split("](", 1)[0] for line in out.splitlines()]
    for label in labels:
        assert "(" not in label and ")" not in label, label


def test_handles_missing_keys_gracefully():
    """Caller may pass an incomplete dict (e.g. one of two uploads failed)."""
    out = _format_artifact_links({"protocol_docx_url": "https://x/p?t=a"})
    assert out == "[📄 Протокол DOCX](https://x/p?t=a)"


def test_handles_none_input():
    assert _format_artifact_links(None) == ""
