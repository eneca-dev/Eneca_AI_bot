---
id: "test-VN-05"
status: "backlog"
priority: "high"
assignee: "Владимир Нестерович"
epic: "test"
dueDate: null
created: "2026-06-23T18:19:54.000Z"
modified: "2026-06-23T18:19:54.000Z"
completedAt: null
labels: ["v0.2.0"]
order: "a5"
---
# test-VN-05 Генерация протокола (TeamsAgent + Author/Graph)

Тестируем по правилам «Человек + Нейросеть». На каждый подтверждённый дефект —
отдельный тикет `bug-VN-NN` со ссылкой сюда.

## Цель
Структурный отчёт MeetingReport: шапка, участники, резюме, разделы (вопросы/
договорённости, открытые вопросы, риски), составитель (Author) и кто пригласил.
Обогащение Author через Microsoft Graph; резолв inviter email.

## Контекст реализации (для проверяющего ИИ)
- `TeamsAgent.process_meeting` (модель `gpt-5.4-mini`) → `MeetingReport` (structured output).
- Author: `_build_author_from_conversation` + `graph_client.get_user_profile` (jobTitle/companyName), fail-open → name-only.
- inviter email: `graph_client.get_user_email` (mail → userPrincipalName, lowercase).

## Среда
Локально через синк `POST /api/teams/process-meeting` (`scratchpad/probe_vn05.py`):
реалистичный русский транскрипт + сохранённый conversation reference с **реальным AAD VN**
(`3c29d86e…`) → реальная генерация (gpt-5.4-mini) + Graph-обогащение + резолв inviter email.
Результат прочитан из строки `meeting_reports` (`scratchpad/probe_read.py`).

## Сценарии (чек-лист)

### 🔴 Приоритет 1 — структура протокола
- [x] **S1. Разделы шаблона.** ✅ Шапка (date/duration/location/**project** «ЖК Северный»/subject), 3 участника с ролями, `preview_summary`, раздел 1 (5 договорённостей с topic/outcome/responsible/deadline/status), раздел 2 (1 откр. вопрос), раздел 3 (2 риска с cause/consequences/mitigation), author — всё по шаблону Eneca.
- [x] **S2. Качество резюме.** ✅ Осмысленное, на русском, соответствует встрече: сроки (нагрузки 2.07 → расчёты 7.07 → рабочка 15.07), эскалация остекления, согласование дымоудаления.

### 🟡 Приоритет 2 — обогащение и авторство
- [x] **S3. Author из Graph.** ✅ `role` подтянут из Graph `jobTitle` («Инженер-программист…»); `organization=null` — корректный fallback (у VN в AAD `companyName` пуст). Graph-профиль реально запрошен (иначе role не появился бы).
- [x] **S4. «Кто пригласил».** ✅ `invited_by_name="Владимир Нестерович"`, `invited_by_aad_object_id=3c29d86e…` — резолв из conversation reference.
- [x] **S5. inviter email.** ✅ `get_user_email` → `vladzimir.nesterovich@enecagroup.com`, **в нижнем регистре** (резолв `mail`/`userPrincipalName` через Graph).

## Найденные баги
_(на каждый подтверждённый баг — отдельный `bug-VN-NN` со ссылкой сюда)_
- _пока нет_

## Наблюдения (не подтверждённые баги)
- **OBS-1 (данные AAD, не баг бота):** в `jobTitle` VN опечатка «искуственному», имя приходит с двойным пробелом «Владимир  Нестерович». Бот корректно отражает то, что лежит в профиле; чинить — на стороне AD, не бота.
- **OBS-2 (real e2e, async):** на реальном recording Author тоже обогащён из Graph (role подтянут), резолв inviter email **в коде сработал** (Graph получил профиль `aad=3c29d86e…`). Но в строку БД `invited_by_*` не попали — это дефект персистентности, не резолва → [[bug-VN-02]] (трекается в test-VN-07).
- **Тест-артефакт (убран):** тестовая строка `meeting_reports` `id=add30ec5-…` (recall_bot_id=NULL, subject «…ЖК Северный») удалена после прогона.
