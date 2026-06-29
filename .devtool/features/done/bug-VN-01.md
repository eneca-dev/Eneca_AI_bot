---
id: "bug-VN-01"
status: "done"
priority: "low"
assignee: null
epic: "bug"
dueDate: null
created: "2026-06-26T17:55:00.000Z"
modified: "2026-06-29T09:10:00.000Z"
completedAt: "2026-06-29T09:10:00.000Z"
labels: ["v0.2.0"]
order: "b1"
---
# bug-VN-01 Zoom-паттерн матчит домен-двойник (`evilzoom.us`)

Найден в ходе QA по [[test-VN-02]] (SEC1). Исполнитель не назначен.

## Симптом
`extract_meeting_url_from_activity` распознаёт как валидную Zoom-встречу ссылку на
**чужой домен, оканчивающийся на `zoom.us`**, например `https://evilzoom.us/j/123456`.
Следствие: бот отправит Recall-ассистента на сторонний URL (домен-двойник / typosquat).

## Причина
`server.py:174`:
```python
re.compile(r'https?://[\w.-]*zoom\.us/[jw]/[^\s<>"]+', re.IGNORECASE)
```
`[\w.-]*` перед `zoom.us` не требует границы поддомена, поэтому `evilzoom.us` тоже
подходит (`evil` + `zoom.us`). Корректный поддомен `us02web.zoom.us` должен проходить,
а приклеенное слово — нет.

## Воспроизведение
Чистая функция (без сервера/Recall):
- `https://evilzoom.us/j/123456` → **возвращается как ссылка** (ожидалось `None`).
- Контроль: `https://us02web.zoom.us/j/85512345678` → ок (встреча); `https://zoom.us.evil.com/j/123` → корректно `None`.

## Ожидаемое vs фактическое
- Ожидалось: матч только для `zoom.us` и его поддоменов (`*.zoom.us`).
- Фактически: матчится любой суффикс `…zoom.us`.

## Предлагаемый фикс
Требовать границу поддомена — точку перед `zoom.us` либо начало хоста:
```python
re.compile(r'https?://([\w-]+\.)*zoom\.us/[jw]/[^\s<>"]+', re.IGNORECASE)
```
`([\w-]+\.)*` допускает `us02web.zoom.us` и голый `zoom.us`, но отклоняет `evilzoom.us`.
Аналогично стоит проверить остальные паттерны на тот же класс ошибки (для `teams.microsoft.com`,
`teams.live.com`, `meet.google.com` хост зафиксирован целиком — там проблемы нет).

## На что обратить внимание ревьюеру
- Не сломать легитимные Zoom-поддомены (`us02web.`, `eu01web.`, корпоративные vanity-домены `companyname.zoom.us`).
- Добавить регресс-тест на `evilzoom.us` (negative) и `us02web.zoom.us` (positive).

## Решение (применено, → review)
1. **Как решено:** в `server.py` паттерн Zoom заменён на
   `r'https?://([\w-]+\.)*zoom\.us/[jw]/[^\s<>"]+'`. Паттерн заякорен на `https?://`,
   а `([\w-]+\.)*` допускает только поддомены через точку — приклеенный префикс (`evil`)
   не проходит. Голый `zoom.us`, `us02web.zoom.us`, vanity `acme.zoom.us`, webinar `/w/` — проходят.
2. **На что смотреть ревьюеру:** регресс-тесты в `tests/test_meeting_link_extraction.py`
   (`test_zoom_real_domains_match` — positive, `test_zoom_lookalike_domains_do_not_match` —
   `evilzoom.us` / `x.evilzoom.us` / `zoom.us.evil.com` → None). Все suite зелёные.
