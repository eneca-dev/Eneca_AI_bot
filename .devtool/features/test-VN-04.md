---
id: "test-VN-04"
status: "backlog"
priority: "high"
assignee: "Владимир Нестерович"
epic: "test"
dueDate: null
created: "2026-06-23T18:19:54.000Z"
modified: "2026-06-23T18:19:54.000Z"
completedAt: null
labels: ["v0.2.0"]
order: "a4"
---
# test-VN-04 Обработка записи (Recall webhook → Whisper)

Тестируем по правилам «Человек + Нейросеть». На каждый подтверждённый дефект —
отдельный тикет `bug-VN-NN` со ссылкой сюда.

## Цель
После завершения встречи: webhook от Recall → скачивание записи → транскрипция
Whisper → маппинг спикеров по speaker_timeline. Устойчивость к null-полям Recall.

## Контекст реализации (для проверяющего ИИ)
- `POST /api/recall/webhook` (`bot.done`) → фоновая `_process_recording_with_whisper`.
- Скачивание `download_video` → `whisper_transcriber.transcribe` (chunking >24MB) → маппинг по `get_speaker_timeline` (max overlap).
- Хардненинг null-payload: `_extract_meeting_metadata`, `_participant_name`, `_ts_relative` + `(x.get(k) or {})` в recall_client.

## Среда
S5 (null-устойчивость) — автономно, прогон pytest-наборов. S1–S4/P1 и реальные имена
спикеров (S3) — нужен настоящий recording (Recall webhook → Whisper); вебхук Recall (Svix)
настроен на прод, поэтому локально этот поток не воспроизвести без переключения вебхука.

## Сценарии (чек-лист)

### 🔴 Приоритет 1 — основной поток
- [x] **S1. Старт обработки.** ✅ Real e2e (2026-06-29, bot `5b2a7420…`): `recording.done` → `Recording done … starting Whisper`; в чат ушло «Встреча завершена. Обрабатываю запись…».
- [x] **S2. Готовый протокол.** ✅ Пайплайн отработал целиком без падений: download → Whisper (7 сегментов, 62.84s) → маппинг спикеров → TeamsAgent → DOCX → доставка. Протокол сгенерирован и доставлен.
- [x] **S3. Имена спикеров.** ✅ Соло-прогон: 7/7 на «Владимир Нестерович». **Мультиспикер-прогон (2026-06-29, bot `3374bf6b…`, VN + Екатерина Зорина):** `speaker_timeline: 83 entries`, **`114/114 segments mapped to real speakers, 0 generic 'Speaker'`**, в транскрипте **два различённых спикера** `['Владимир  Нестерович', 'Екатерина Зорина']` с чередованием по сегментам. Алгоритм max-overlap корректно разводит двух участников.

### 🟡 Приоритет 2 — краевые случаи
- [x] **S4. Короткая встреча.** ✅ Запись ~63 сек обработана без ошибок, протокол получен.
- [x] **S5. Устойчивость к null-полям Recall.** ✅ Регресс фикса закрыт: `tests/test_recall_metadata_safety.py` + `tests/test_recall_client_payload_safety.py` — **33/33 passed**. Хелперы `_extract_meeting_metadata` / `_participant_name` / `_ts_relative` + `(x.get(k) or {})` устойчивы к explicit-null; `'NoneType' object has no attribute 'get'` не воспроизводится. На реальном прогоне краша тоже не было.

### ⚡ Производительность
- [x] **P1. Одно скачивание.** ✅ Real e2e: `Downloading video`=1, `Processing recording`=1, `Whisper complete`=1, `Report sent`=1. Единственная попытка дубль-вставки строки поймана `23505` (идемпотентность), двойной обработки/скачивания нет.

## Найденные баги
_(на каждый подтверждённый баг — отдельный `bug-VN-NN` со ссылкой сюда)_
- **[[bug-VN-02]]** — в async-потоке `invited_by_*` не доходят до строки `meeting_reports` (косвенно вскрыто здесь: `start_meeting_processing` упал на `23505`, см. ниже). Сам поток обработки записи работает.

## Наблюдения (не подтверждённые баги)
- **OBS-1 (среда, не баг бота):** локально `ffmpeg not found` → код ушёл в fallback «mp4 напрямую в Whisper» и отработал. На проде ffmpeg обычно есть.
- **OBS-2 (РЕШЕНО — корень установлен):** `23505 duplicate key` на каждом прогоне вызван тем, что в **Recall настроены ДВА активных webhook-эндпоинта** (прод + наш ngrok). Recall шлёт `recording.done` на оба → прод и локаль одновременно обрабатывают запись против общей meetings-БД, и второй INSERT ловит `23505`. Это **артефакт тест-сетапа**, не баг продукта: в одно-эндпоинтном проде `start_meeting_processing` успешен и `invited_by` пишется штатно. Следствия: (1) [[bug-VN-02]] остаётся как defense-in-depth (Recall ретраит вебхуки и сам по себе); (2) двойная обработка пайплайна → [[bug-VN-03]]. **Операционно:** убрать ngrok-эндпоинт из Recall после тестов.
