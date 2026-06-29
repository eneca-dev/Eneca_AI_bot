---
id: "bug-VN-02"
status: "done"
priority: "medium"
assignee: null
epic: "bug"
dueDate: null
created: "2026-06-29T07:30:00.000Z"
modified: "2026-06-29T09:10:00.000Z"
completedAt: "2026-06-29T09:10:00.000Z"
labels: ["v0.2.0"]
order: "b2"
---
# bug-VN-02 invited_by_* теряются в async-потоке (complete_meeting_report не пишет их в UPDATE)

Найден в реальном e2e по [[test-VN-04]] / [[test-VN-05]] / [[test-VN-07]] (real recording,
recall_bot_id=`5b2a7420-9f6a-4356-97b1-9d96b1a152a4`). Исполнитель не назначен.

## Симптом
После реальной обработки записи строка `meeting_reports` сохранена с
`invited_by_aad_object_id = invited_by_name = invited_by_email = NULL`, хотя:
- при join инвайтер был захвачен (`join_meeting` залогировал `invited_by='Владимир Нестерович'`);
- в обработке Graph **успешно** резолвнул профиль `aad=3c29d86e…` → email был получен;
- на синк-потоке (`/api/teams/process-meeting`, test-VN-05) тот же email пишется корректно.

Дашборд сопоставляет встречу с владельцем по `invited_by_email` — при NULL атрибуция теряется.

## Причина (детерминированная)
`complete_meeting_report` (database/meetings_client.py) в обычном пути делает **UPDATE**,
а `update_row` (≈ строки 158-170) **не содержит** `invited_by_aad_object_id/name/email`
и `meeting_started_at` — эти поля передаются только в *fallback* `upsert_meeting_report`
(когда строки нет). Значит owner-поля выживают, только если их успел записать
`start_meeting_processing` (INSERT). Если INSERT на старте не прошёл — `complete` их НЕ дозаписывает.

Здесь INSERT в `start_meeting_processing` упал на `23505 duplicate key` (строка с этим
`recall_bot_id` уже существовала к моменту вызова) → инвайтер не записан → `complete`
его не восстановил → NULL.

## Воспроизведение
Реальный созвон (бот join → запись → завершение). В логе:
```
join_meeting … invited_by='Владимир  Нестерович'
Graph profile fetched: aad=3c29d86e-…           # email резолвнут
start_meeting_processing: row already exists … 23505 duplicate key
Meeting report completed: id=369c6e92-… costs=…  # UPDATE без invited_by
```
Итоговая строка: `invited_by_* = NULL`, при этом `costs`, `*_docx_url`, `meeting_started_at`, `report`, `transcript` — заполнены.

## Предлагаемый фикс
Сделать `complete_meeting_report` авторитетным по owner-полям: добавить их в обычный `update_row`,
но **не затирать** существующие значения None'ом (писать только непустые). Напр.:
```python
update_row = { ...,  # status/report/transcript/costs/urls как сейчас
}
for col, val in (
    ("invited_by_aad_object_id", invited_by_aad_object_id),
    ("invited_by_name", invited_by_name),
    ("invited_by_email", invited_by_email),
    ("meeting_started_at", meeting_started_at),
):
    if val is not None:
        update_row[col] = val
```
Тогда даже при сбое INSERT на старте инвайтер дозапишется на завершении.

## Вторично (нужен отдельный repro)
Откуда `23505` при ЕДИНСТВЕННОМ `recording.done` и без залогированного успешного INSERT — не ясно
(возможна повторная доставка вебхука Recall либо ретрай supabase/httpx-клиента, где первая
вставка прошла серверно без owner-полей). Фикс выше делает систему устойчивой к этому независимо
от первопричины, но стоит подтвердить источник дубля отдельно.

## На что обратить внимание ревьюеру
- Не затирать `invited_by_*`/`meeting_started_at` значением None (важно при ретраях webhook — иначе
  поздний пустой вызов сотрёт заполненные поля). Писать только непустое.
- Добавить регресс-тест: существующая `processing`-строка без инвайтера + `complete_meeting_report`
  с непустым инвайтером → поля заполняются.

## Решение (применено, → review)
1. **Как решено:** в `database/meetings_client.py` `complete_meeting_report` после сборки
   `update_row` дозаписывает owner/start-поля, **только если значение непустое**:
   ```python
   for col, val in (("invited_by_aad_object_id", invited_by_aad_object_id),
                    ("invited_by_name", invited_by_name),
                    ("invited_by_email", invited_by_email),
                    ("meeting_started_at", meeting_started_at)):
       if val is not None:
           update_row[col] = val
   ```
   Теперь даже если INSERT в `start_meeting_processing` пропущен (как при `23505`-гонке),
   инвайтер дозаписывается на завершении; пустой поздний ретрай ничего не затирает.
2. **На что смотреть ревьюеру:** регресс-тесты в `tests/test_meetings_client.py`
   (`test_complete_meeting_report_backfills_invited_by_on_update`,
   `test_complete_meeting_report_does_not_wipe_owner_fields_with_none`). Доп. проверено живой
   записью в meetings-БД (seed-строка без инвайтера → complete с инвайтером → поля заполнены;
   пустой ретрай не стёр). Все suite зелёные (77 passed).

> Первопричина `23505`-дубля УСТАНОВЛЕНА: в Recall было два активных webhook-эндпоинта (прод + ngrok),
> оба обрабатывали запись против общей БД (см. OBS-2 в [[test-VN-04]]). Это артефакт тест-сетапа —
> в одно-эндпоинтном проде INSERT в `start_meeting_processing` успешен и пишет инвайтера. Фикс выше
> оставляем как defense-in-depth (Recall ретраит доставку и сам). Двойная обработка пайплайна вынесена в [[bug-VN-03]].
