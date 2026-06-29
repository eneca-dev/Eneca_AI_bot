---
id: "test-VN-01"
status: "backlog"
priority: "medium"
assignee: "Владимир Нестерович"
epic: "test"
dueDate: null
created: "2026-06-23T18:19:54.000Z"
modified: "2026-06-23T18:19:54.000Z"
completedAt: null
labels: ["v0.2.0"]
order: "a1"
---
# test-VN-01 Онбординг бота / привязка чата

Тестируем по правилам «Человек + Нейросеть» (как в `EnecaWork/test-VN-01`):
тестировщик пишет боту, ИИ ведёт сценарии, читает логи/состояние и проверяет.
На каждый подтверждённый дефект — отдельный тикет `bug-VN-NN` со ссылкой сюда.

## Цель
Первое сообщение боту EnecaProtocolMeetBot: сохранение conversation reference и
приветствие. Без этого протокол потом некуда слать.

## Контекст реализации (для проверяющего ИИ)
- Эндпоинт: `POST /api/messages` (Bot Framework) в `server.py` → `teams_messages_endpoint`.
- При `type == "message"`: `teams_sender.save_conversation_reference(activity)` → приветствие.
- Reference хранит: conversation id, `user_name`, `user_aad_object_id`.

## Среда
Локально: `server.py` на :8000 + ngrok (`paige-unpractical-britteny.ngrok-free.dev`),
Azure messaging endpoint → `<ngrok>/api/messages`. Тестировщик пишет боту в Teams,
ИИ читает захваченные логи локального сервера.

## Сценарии (чек-лист)

### 🔴 Приоритет 1 — базовый онбординг
- [x] **S1. Первое сообщение боту.** ✅ **Real e2e подтверждён** (2026-06-26, реальный Teams, edge IP `52.123.136.98` = Microsoft): `type=message, from=Владимир Нестерович` → бот ответил приветствием, тестировщик подтвердил получение в чате. Цепочка чистая: reference saved → OAuth token acquired → `POST /api/messages 200 OK` без ошибок. Блокер доставки из OBS-1 устранён переключением Azure endpoint на актуальный ngrok.
- [x] **S2. Сохранение reference.** ✅ Real e2e: `Saved conversation reference for user 'Владимир Нестерович' (conv_id=a:1Biszcv0eN…)` — настоящий Teams conv_id; reference содержит `user_name`, `conversation_id`, `user_aad_object_id` (хранится под conv_id и под aadObjectId).

### 🟡 Приоритет 2 — повторные / множественные чаты
- [x] **S3. Повторное сообщение из того же чата.** ✅ Real e2e (2026-06-26, `тест 2`): второй `save_conversation_reference` под тем же `conv_id=a:1Biszcv0eN…`; `GET /api/teams/conversations` → ровно одна запись на conv_id (ключ словаря = conv_id, перезапись, не дубль). Бонус: второй ответ ушёл на кэшированном OAuth-токене (нет повторного `OAuth token acquired`).
- [x] **S4. Сообщение из другого чата.** ✅ Real e2e (2026-06-29, 2 участника): коллега (Екатерина Зорина, aad `53fdb1a7…`) написала боту в свою личку → сохранился **второй отдельный** reference (`conv_id=a:1_2lHsF6…`), первый (VN, aad `3c29d86e…`, `a:1Biszcv0eN…`) **не затёрт**. `GET /api/teams/conversations` → 2 записи.
- [x] **SEC1. Изоляция чатов.** ✅ Real e2e: приветствие пришло **только** в чат отправителя — Екатерина получила своё в своём чате, VN ничего лишнего не получил (подтверждено обоими). Код-уровень: `reply_to_activity` отвечает строго в `conversation` входящей активити, references раздельны по `conv_id`/`aadObjectId` — утечки нет.

### ⚡ Производительность
- [x] **P1. Сетевой профиль.** ✅ Real e2e: на каждое сообщение ровно одна activity `type=message`, один `save_conversation_reference`, один `POST /api/messages 200 OK`. Дублей обработки/ответов нет.

## Найденные баги
_(на каждый подтверждённый баг — отдельный `bug-VN-NN` со ссылкой сюда)_
- _пока нет_

## Наблюдения (не подтверждённые баги)
- **OBS-3 (среда/тест-канал, НЕ баг продукта):** при тесте через Azure **Web Chat** ответ
  падает `400 MissingProperty: The 'Activity.From' field is required` — Web Chat требует
  `from` в payload явно, а `reply_to_activity` его не шлёт. В **реальном Teams ошибки нет**
  (канал сам подставляет `from`), поэтому пользователей это не затрагивает и тикет не заводим.
  Двойной слэш `//v3` в URL Bot Framework игнорирует (проверено: оба варианта URL дают тот же 400).
  Если позже захотим использовать Web Chat как локальный QA-канал — добавить `from=recipient`/
  `recipient=from` в `teams_sender.reply_to_activity`/`send_message`.
- **OBS-1 (РЕШЕНО):** причина «через ngrok шёл только `GET /health`» — Azure messaging endpoint
  вёл не на актуальный ngrok (сообщения уходили на прежний endpoint). После переключения endpoint
  на живой `paige-...ngrok-free.dev/api/messages` входящие активити долетают (S1/S2 real e2e ✅).
- **OBS-2 (артефакт тестирования, НЕ канал-баг):** ошибка канала Teams «Failed to decrypt
  conversation id» в 22:16 вызвана синтетическим тестом (вариант Б, 22:15:57): ИИ отправил
  ответ с фейковым conversation id `a:synthetic-conv-VN-1` на реальный Teams service URL →
  Teams не смог его расшифровать (отсюда же 403). К входящей доставке реальных сообщений
  отношения не имеет.
