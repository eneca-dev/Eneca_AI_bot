"""Tests for cost_calculator — pure arithmetic against settings prices."""
from unittest.mock import patch

import pytest

from services import cost_calculator


@pytest.fixture
def fake_prices():
    with patch("services.cost_calculator.settings") as s:
        s.price_llm_input_per_1m_usd = 0.75
        s.price_llm_output_per_1m_usd = 4.50
        s.price_whisper_per_min_usd = 0.006
        s.price_recall_per_hour_usd = 0.50
        yield s


# --- LLM ---


def test_llm_cost_typical_call(fake_prices):
    # 12 000 input tokens × $0.75/1M  = $0.009
    # 1 500 output tokens × $4.50/1M = $0.00675
    # total ≈ $0.01575 → round to $0.0158
    assert cost_calculator.llm_cost_usd(12_000, 1_500) == round(0.009 + 0.00675, 4)


def test_llm_cost_zero_returns_none(fake_prices):
    assert cost_calculator.llm_cost_usd(0, 0) is None
    assert cost_calculator.llm_cost_usd(None, None) is None


def test_llm_cost_handles_partial_usage(fake_prices):
    """If only input or only output is reported — count the one we have."""
    assert cost_calculator.llm_cost_usd(1_000_000, 0) == 0.75
    assert cost_calculator.llm_cost_usd(0, 1_000_000) == 4.50


# --- Whisper ---


def test_whisper_cost_one_hour(fake_prices):
    # 60 minutes × $0.006 = $0.36
    assert cost_calculator.whisper_cost_usd(3600) == 0.36


def test_whisper_cost_short_meeting(fake_prices):
    # 65 sec ≈ 1.0833 min × $0.006 ≈ $0.0065
    assert cost_calculator.whisper_cost_usd(65) == 0.0065


def test_whisper_cost_zero_or_negative_returns_none(fake_prices):
    assert cost_calculator.whisper_cost_usd(0) is None
    assert cost_calculator.whisper_cost_usd(-5) is None
    assert cost_calculator.whisper_cost_usd(None) is None


# --- Recall ---


def test_recall_cost_one_hour(fake_prices):
    # 3600 sec = 1 hour × $0.50 = $0.50
    assert cost_calculator.recall_cost_usd(3600) == 0.50


def test_recall_cost_partial_hour(fake_prices):
    # 1800 sec = 0.5 hour × $0.50 = $0.25
    assert cost_calculator.recall_cost_usd(1800) == 0.25


def test_recall_cost_zero_returns_none(fake_prices):
    assert cost_calculator.recall_cost_usd(0) is None
    assert cost_calculator.recall_cost_usd(None) is None


# --- Smoke math: a 1-hour meeting end-to-end ---


def test_typical_one_hour_meeting_total_under_one_dollar(fake_prices):
    """Sanity check from the conversation: ~$0.88 for a 1h meeting."""
    llm = cost_calculator.llm_cost_usd(15_000, 3_000)        # ≈ 0.0248
    whisper = cost_calculator.whisper_cost_usd(3600)          # 0.36
    recall = cost_calculator.recall_cost_usd(3600)            # 0.50
    total = (llm or 0) + (whisper or 0) + (recall or 0)
    assert 0.85 < total < 0.95
