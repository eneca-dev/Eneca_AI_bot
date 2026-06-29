---
id: "test-VN-02"
status: "backlog"
priority: "high"
assignee: "Владимир Нестерович"
epic: "test"
dueDate: null
created: "2026-06-23T18:19:54.000Z"
modified: "2026-06-23T18:19:54.000Z"
completedAt: null
labels: ["v0.2.0"]
order: "a2"
---
# test-VN-02 Распознавание ссылки на встречу

Тестируем по правилам «Человек + Нейросеть». На каждый подтверждённый дефект —
отдельный тикет `bug-VN-NN` со ссылкой сюда.

## Цель
Извлечение ссылки из активности Teams: голый URL, ссылка-лейбл (URL спрятан в
attachments / tap.value), поддерживаемые площадки, игнор не-встречных ссылок.

## Контекст реализации (для проверяющего ИИ)
- `extract_meeting_url_from_activity(activity)` обходит ВСЕ строки payload (текст + attachments).
- `MEETING_URL_PATTERNS` (server.py): teams.microsoft.com (`/meet`, `/l/meetup-join`), teams.live.com, `*zoom.us/[jw]/`, meet.google.com.
- Регресс: раньше читался только `activity["text"]` — ссылка-лейбл не распознавалась.

## Среда
Логику распознавания проверяем напрямую как **чистую функцию** `extract_meeting_url_from_activity`
(без сервера/Recall — реальная отправка ссылки в Teams вызвала бы живой Recall-бот, это scope test-VN-03).
Real e2e позитива — в test-VN-03. Прогон: `scratchpad/probe_links.py`, 13 кейсов.

## Сценарии (чек-лист)

### 🔴 Приоритет 1 — основные форматы
- [x] **S1. Голый Teams URL в тексте.** ✅ Распознаны все три: `teams.microsoft.com/l/meetup-join/…`, `teams.microsoft.com/meet/…`, `teams.live.com/meet/…`.
- [x] **S2. Ссылка-лейбл (анкор).** ✅ URL спрятан в `attachments[*].content.tap.value` (HeroCard), текст = только лейбл → извлечён (регресс-кейс закрыт, `_iter_strings` обходит весь payload).
- [x] **S3. Zoom.** ✅ `https://us02web.zoom.us/j/85512345678?pwd=…` распознан.
- [x] **S4. Google Meet.** ✅ `https://meet.google.com/abc-defg-hij` распознан.

### 🟡 Приоритет 2 — негативные
- [x] **S5. Сообщение без ссылки.** ✅ → `None`, подключения нет.
- [x] **S6. Сторонний URL (не встреча).** ✅ google search / youtube → `None`.

### 🔒 Безопасность
- [x] **SEC1. Инъекция в тексте.** ✅ Мусор/SQL-инъекция, teams-канал (не встреча), `zoom.us.evil.com` → `None`. Найденный дефект с доменом-двойником `evilzoom.us` **исправлен** → [[bug-VN-01]] (status review): паттерн заякорен на границу поддомена, регресс-тесты зелёные.

## Найденные баги
_(на каждый подтверждённый баг — отдельный `bug-VN-NN` со ссылкой сюда)_
- **[[bug-VN-01]]** — Zoom-паттерн матчит домен-двойник (`evilzoom.us`), `server.py:174`.

## Наблюдения (не подтверждённые баги)
- _пока нет_
