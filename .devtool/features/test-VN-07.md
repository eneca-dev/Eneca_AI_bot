---
id: "test-VN-07"
status: "backlog"
priority: "medium"
assignee: "Владимир Нестерович"
epic: "test"
dueDate: null
created: "2026-06-23T18:19:54.000Z"
modified: "2026-06-23T18:19:54.000Z"
completedAt: null
labels: ["v0.2.0"]
order: "a7"
---
# test-VN-07 Персистентность (meeting_reports)

Тестируем по правилам «Человек + Нейросеть». На каждый подтверждённый дефект —
отдельный тикет `bug-VN-NN` со ссылкой сюда.

## Цель
Жизненный цикл строки в `meeting_reports` (status processing/done/error, costs,
urls, invited_by_*), идемпотентность ретраев webhook. Корректность данных, которые
Teams-агент кладёт в БД (сам UI `/meetings` — проект EnecaWork, вне scope).

## Контекст реализации (для проверяющего ИИ)
- `meetings_db_client`: `start_meeting_processing` → `processing`; `complete_meeting_report` → `done`; `mark_meeting_error` → `error`.
- UPSERT по `recall_bot_id` (идемпотентность ретраев webhook). Fail-open: ошибки персиста не ломают доставку в Teams.
- Колонки: `report`, `transcript`, `llm/whisper/recall_cost_usd`, `protocol/transcript_docx_url`, `invited_by_aad_object_id/name/email`, `meeting_started_at`.

## Среда
Локально, прямой прогон жизненного цикла через `meetings_db_client` против реального
meetings-проекта (`scratchpad/probe_vn07.py`, 15/15). Тестовые строки `recall_bot_id="qa-test-vn07-*"`
создаются и удаляются автоматически. S5 сверена с `profiles.email` в чат-проекте.

## Сценарии (чек-лист)

### 🔴 Приоритет 1 — жизненный цикл строки
- [x] **S1. processing.** ✅ `start_meeting_processing` → строка `status=processing`; `invited_by_*` и `meeting_started_at` проставлены сразу (известны на старте).
- [x] **S2. done.** ✅ `complete_meeting_report` → `status=done`; заполнены `report`/`transcript`/costs/`protocol_docx_url`/`transcript_docx_url`; `invited_by_*` и `meeting_started_at` **сохраняются** при завершении (UPDATE не затирает старт-поля).
- [x] **S3. error.** ✅ `mark_meeting_error` → `status=error` + информативный `error_message`; ровно одна строка.

### 🔴 Приоритет 1 — идемпотентность
- [x] **S4. Ретрай webhook.** ✅ Повторный `start_meeting_processing` → **одна строка** на `recall_bot_id`, существующую НЕ перезаписывает (subject остался «QA VN-07», не «DIFFERENT» — ключевая защита от сброса `done`→`processing`). Повторный `complete_meeting_report` тоже не плодит дубли.

### 🟡 Приоритет 2 — поля владельца и стоимости
- [x] **S5. invited_by_email.** Синк-поток ✅ (нижний регистр + точное совпадение с `profiles.email`: для `vladzimir.nesterovich@enecagroup.com` ровно 1 строка). Async-поток: исходно `NULL` на реальном recording (bot `5b2a7420…`) → **исправлено** [[bug-VN-02]] (status review): `complete_meeting_report` теперь дозаписывает `invited_by_*` на завершении (не затирая непустое). Проверено регресс-тестами + живой записью в БД.
- [x] **S6. costs.** ✅ Прямой прогон: 0.0123/0.0045/0.25; **real e2e**: 0.0044/0.0063/0.0087 (из реального usage). В синк-потоке (test-VN-05) обоснованно `NULL` — стоимость там не измеряется.

## Найденные баги
_(на каждый подтверждённый баг — отдельный `bug-VN-NN` со ссылкой сюда)_
- **[[bug-VN-02]]** — `invited_by_*` теряются в async-потоке (`complete_meeting_report` не пишет их в обычном UPDATE).

## Наблюдения (не подтверждённые баги)
- **Real e2e (2026-06-29, bot `5b2a7420…`):** жизненный цикл подтверждён на живых данных — `processing`(через `23505`-идемпотентность) → `done`, `report`/`transcript`/costs/`*_docx_url`/`meeting_started_at` заполнены; обе DOCX-ссылки отдают HTTP 200. Единственный провал — `invited_by_*` (bug-VN-02).
- **Пост-фикс real e2e (2026-06-29, bot `3374bf6b…`, мультиспикер):** тот же `23505 duplicate` повторился (дубль воспроизводим), **но `invited_by_*` теперь заполнены** (`aad=3c29d86e…`, email `vladzimir.nesterovich@enecagroup.com` lowercase) + `meeting_started_at` + реальные costs. Фикс [[bug-VN-02]] подтверждён против реального условия, которое ломало раньше.
