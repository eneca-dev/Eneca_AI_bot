"""Smoke test for the Meetings Supabase project.

Runs two end-to-end scenarios against the real Supabase project pointed at by
SUPABASE_MEETINGS_URL / SUPABASE_MEETINGS_SERVICE_KEY:

  1. Happy path : start_processing  -> complete_meeting_report (status: processing -> done)
  2. Fail  path : start_processing  -> mark_meeting_error      (status: processing -> error)

Usage (from project root, with virtualenv active):
    python scripts/test_meeting_persist.py            # cleans up after itself
    python scripts/test_meeting_persist.py --keep     # leaves rows for inspection
"""
import sys
import time
from datetime import date
from pathlib import Path

# Make project root importable when running as `python scripts/test_meeting_persist.py`
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _print(msg: str) -> None:
    print(msg, flush=True)


def _sample_report(today: str) -> dict:
    return {
        "subject": "Smoke Test — happy path",
        "date": today,
        "duration": "0h 5m",
        "project": None,
        "location": "Microsoft Teams",
        "transcript_url": None,
        "previous_protocol_url": None,
        "participants": [
            {"organization": "Eneca", "name": "Иван Тестовый", "role": "QA"},
        ],
        "preview_summary": "Smoke-тест двухфазной записи в БД.",
        "discussion_items": [
            {
                "topic": "Проверка двухфазной записи",
                "outcome": "Перешли processing → done. Если видишь это — ок.",
                "responsible": "Иван Тестовый",
                "deadline": "сегодня",
                "status": "Выполнено",
            },
        ],
        "open_questions": [],
        "risks": [],
        "author": {
            "organization": "Eneca",
            "name": "Meeting Bot",
            "role": "Автоматический протокол",
        },
    }


def _sample_transcript(today: str) -> dict:
    return {
        "title": "Smoke Test — happy path",
        "date": today,
        "duration": "0h 5m",
        "participants": [
            {"organization": "Eneca", "name": "Иван Тестовый", "role": "QA"},
        ],
        "transcript": [
            {"speaker": "Иван Тестовый", "timestamp": "00:00",
             "text": "Запускаю smoke-тест."},
            {"speaker": "Иван Тестовый", "timestamp": "00:15",
             "text": "Проверяю переход processing → done."},
        ],
    }


def _delete_row(client, recall_bot_id: str) -> None:
    try:
        client.table("meeting_reports").delete().eq("recall_bot_id", recall_bot_id).execute()
        _print(f"  Deleted {recall_bot_id}")
    except Exception as e:
        _print(f"  Cleanup of {recall_bot_id} failed (ignore): {e}")


def _check(condition: bool, message: str) -> bool:
    icon = "OK  " if condition else "FAIL"
    _print(f"  [{icon}] {message}")
    return condition


def _scenario_happy(meetings_db_client, today: str, recall_bot_id: str) -> bool:
    _print(f"\n--- Happy path (recall_bot_id={recall_bot_id}) ---")

    started = meetings_db_client.start_meeting_processing(
        recall_bot_id=recall_bot_id,
        subject="Smoke Test — happy path",
        meeting_date=today,
    )
    if not started:
        _print("  start_meeting_processing returned None — aborting scenario")
        return False

    row = meetings_db_client.get_meeting_report_by_bot_id(recall_bot_id)
    ok1 = _check(row is not None and row.get("status") == "processing",
                 f"status='processing' after start (got {row and row.get('status')!r})")
    ok2 = _check(row is not None and row.get("report") is None,
                 "report is NULL during processing")

    fake_costs = {"llm_cost_usd": 0.02, "whisper_cost_usd": 0.36, "recall_cost_usd": 0.50}
    fake_urls = {
        "protocol_docx_url": f"https://example.test/{recall_bot_id}/protocol.docx",
        "transcript_docx_url": f"https://example.test/{recall_bot_id}/transcript.docx",
    }

    completed = meetings_db_client.complete_meeting_report(
        recall_bot_id=recall_bot_id,
        report=_sample_report(today),
        transcript=_sample_transcript(today),
        costs=fake_costs,
        urls=fake_urls,
    )
    ok3 = _check(completed is not None and completed.get("status") == "done",
                 f"status='done' after complete (got {completed and completed.get('status')!r})")

    row2 = meetings_db_client.get_meeting_report_by_bot_id(recall_bot_id)
    ok4 = _check(row2 is not None and row2.get("report") is not None,
                 "report is filled after complete")
    ok5 = _check(row2 is not None and row2.get("transcript") is not None,
                 "transcript is filled after complete")
    ok6 = _check(row2 is not None and row2.get("error_message") is None,
                 "error_message stays NULL on success")
    ok7 = _check(
        row2 is not None and float(row2.get("llm_cost_usd") or 0) == 0.02,
        f"llm_cost_usd persisted (got {row2 and row2.get('llm_cost_usd')!r})",
    )
    ok8 = _check(
        row2 is not None and float(row2.get("whisper_cost_usd") or 0) == 0.36,
        f"whisper_cost_usd persisted (got {row2 and row2.get('whisper_cost_usd')!r})",
    )
    ok9 = _check(
        row2 is not None and float(row2.get("recall_cost_usd") or 0) == 0.50,
        f"recall_cost_usd persisted (got {row2 and row2.get('recall_cost_usd')!r})",
    )
    ok10 = _check(
        row2 is not None and abs(float(row2.get("total_cost_usd") or 0) - 0.88) < 0.01,
        f"total_cost_usd auto-computed (got {row2 and row2.get('total_cost_usd')!r}, expected ~0.88)",
    )
    ok11 = _check(
        row2 is not None and row2.get("protocol_docx_url") == fake_urls["protocol_docx_url"],
        "protocol_docx_url persisted",
    )
    ok12 = _check(
        row2 is not None and row2.get("transcript_docx_url") == fake_urls["transcript_docx_url"],
        "transcript_docx_url persisted",
    )

    return all([ok1, ok2, ok3, ok4, ok5, ok6, ok7, ok8, ok9, ok10, ok11, ok12])


def _scenario_fail(meetings_db_client, today: str, recall_bot_id: str) -> bool:
    _print(f"\n--- Fail path (recall_bot_id={recall_bot_id}) ---")

    started = meetings_db_client.start_meeting_processing(
        recall_bot_id=recall_bot_id,
        subject="Smoke Test — fail path",
        meeting_date=today,
    )
    if not started:
        _print("  start_meeting_processing returned None — aborting scenario")
        return False

    err_msg = "Whisper returned 0 segments — no speech detected"
    failed = meetings_db_client.mark_meeting_error(recall_bot_id, err_msg)
    ok1 = _check(failed is not None and failed.get("status") == "error",
                 f"status='error' after mark_error (got {failed and failed.get('status')!r})")

    row = meetings_db_client.get_meeting_report_by_bot_id(recall_bot_id)
    ok2 = _check(row is not None and row.get("error_message") == err_msg,
                 "error_message persisted")
    ok3 = _check(row is not None and row.get("report") is None,
                 "report stays NULL on failure")

    return all([ok1, ok2, ok3])


def _scenario_dedup(meetings_db_client, today: str, recall_bot_id: str) -> bool:
    """Recall webhook retry: start_meeting_processing called twice for the same bot id."""
    _print(f"\n--- Dedup (webhook retry) (recall_bot_id={recall_bot_id}) ---")

    first = meetings_db_client.start_meeting_processing(recall_bot_id, subject="dedup", meeting_date=today)
    if not first:
        _print("  first start returned None — aborting")
        return False
    second = meetings_db_client.start_meeting_processing(recall_bot_id, subject="dedup", meeting_date=today)

    ok1 = _check(second is not None, "second start returned the existing row (no exception bubbled)")
    ok2 = _check(first.get("id") == (second or {}).get("id"),
                 f"both calls reference same id (first={first.get('id')}, second={second and second.get('id')})")
    return all([ok1, ok2])


def main() -> int:
    _print("Loading settings + Supabase client...")
    from core.config import settings
    from database.meetings_client import meetings_db_client

    _print("\n--- Config check ---")
    _print(f"SUPABASE_MEETINGS_URL set:         {bool(settings.supabase_meetings_url)}")
    _print(f"SUPABASE_MEETINGS_SERVICE_KEY set: {bool(settings.supabase_meetings_service_key)}")
    _print(f"Client available:                  {meetings_db_client.is_available()}")

    if not meetings_db_client.is_available():
        _print("\nClient is not available. Add SUPABASE_MEETINGS_URL and "
               "SUPABASE_MEETINGS_SERVICE_KEY to .env, then re-run.")
        return 1

    today = date.today().isoformat()
    ts = int(time.time())
    keep = "--keep" in sys.argv

    bot_happy = f"smoke-happy-{ts}"
    bot_fail = f"smoke-fail-{ts}"
    bot_dedup = f"smoke-dedup-{ts}"

    happy_ok = _scenario_happy(meetings_db_client, today, bot_happy)
    fail_ok = _scenario_fail(meetings_db_client, today, bot_fail)
    dedup_ok = _scenario_dedup(meetings_db_client, today, bot_dedup)

    _print("\n--- Summary ---")
    _print(f"  Happy path: {'OK' if happy_ok else 'FAIL'}")
    _print(f"  Fail path:  {'OK' if fail_ok else 'FAIL'}")
    _print(f"  Dedup:      {'OK' if dedup_ok else 'FAIL'}")

    if keep:
        _print(f"\n--keep set — left rows in the table: {bot_happy}, {bot_fail}, {bot_dedup}")
        _print("Inspect them in Supabase → Table Editor → meeting_reports.")
    else:
        _print("\n--- Cleanup ---")
        for bot in (bot_happy, bot_fail, bot_dedup):
            _delete_row(meetings_db_client.client, bot)
        _print("Pass --keep to skip cleanup and inspect rows in Supabase UI.")

    all_ok = happy_ok and fail_ok and dedup_ok
    _print(f"\n{'All good.' if all_ok else 'Some scenarios failed — see above.'}")
    return 0 if all_ok else 2


if __name__ == "__main__":
    sys.exit(main())
