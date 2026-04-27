"""Cost calculation for the Teams meeting pipeline.

Pure functions that convert raw usage units (tokens, seconds) into USD
based on prices configured in the environment (see core/config.py).

All functions return `None` for missing/zero usage so the caller can
distinguish "not measured" from "actually zero".
"""
from typing import Optional

from core.config import settings


def llm_cost_usd(input_tokens: Optional[int], output_tokens: Optional[int]) -> Optional[float]:
    """Cost of one LLM call from token counts. Returns None if both inputs are missing."""
    if not input_tokens and not output_tokens:
        return None
    in_tokens = input_tokens or 0
    out_tokens = output_tokens or 0
    in_usd = (in_tokens / 1_000_000) * settings.price_llm_input_per_1m_usd
    out_usd = (out_tokens / 1_000_000) * settings.price_llm_output_per_1m_usd
    return round(in_usd + out_usd, 4)


def whisper_cost_usd(audio_seconds: Optional[float]) -> Optional[float]:
    """Cost of Whisper transcription based on audio duration."""
    if not audio_seconds or audio_seconds <= 0:
        return None
    minutes = audio_seconds / 60.0
    return round(minutes * settings.price_whisper_per_min_usd, 4)


def recall_cost_usd(recording_seconds: Optional[float]) -> Optional[float]:
    """Cost of Recall.ai recording bot based on recording duration."""
    if not recording_seconds or recording_seconds <= 0:
        return None
    hours = recording_seconds / 3600.0
    return round(hours * settings.price_recall_per_hour_usd, 4)
