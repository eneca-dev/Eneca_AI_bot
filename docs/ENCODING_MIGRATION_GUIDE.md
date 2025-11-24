# Руководство по миграции кодировки документов

## Проблема

Документы в Supabase имеют некорректную кодировку (Windows-1251/Latin1 вместо UTF-8), из-за чего русский текст отображается как "������" или другие искажённые символы.

## Решение

Создан скрипт миграции `scripts/fix_encoding_migration.py`, который:

1. ✅ Экспортирует все документы из Supabase
2. ✅ Автоматически определяет и исправляет кодировку
3. ✅ Создаёт backup перед изменениями
4. ✅ Показывает preview исправлений
5. ✅ Загружает исправленные документы обратно
6. ✅ Генерирует новые embeddings с корректным текстом

---

## Использование

### Шаг 1: Dry Run (предварительный просмотр)

Запустите скрипт без флага `--execute` для анализа:

```bash
python scripts/fix_encoding_migration.py
```

**Что произойдёт:**
- Экспорт всех документов
- Анализ проблем с кодировкой
- Показ статистики и примеров исправлений
- **НЕ вносит изменения** в базу данных

**Пример вывода:**
```
============================================================
РЕЗУЛЬТАТЫ АНАЛИЗА
============================================================
Всего документов: 150
Требуют исправления: 120
В порядке: 30

Использованные стратегии:
  latin1→utf-8: 80 документов
  cp1251→utf-8: 40 документов

Примеры исправлений:
Документ ID: 5 (стратегия: latin1→utf-8)
Original: Ð ÐµÐ±Ð¾Ñ‚Ð° Ñ Ð´Ð¾ÐºÑƒÐ¼ÐµÐ½Ñ‚Ð°Ð¼Ð¸...
Fixed:    Работа с документами...
```

### Шаг 2: Выполнение миграции

Если предварительный просмотр показал корректные исправления:

```bash
python scripts/fix_encoding_migration.py --execute
```

**Что произойдёт:**
1. Создаст backup в `data/backups/documents_backup_YYYYMMDD_HHMMSS.json`
2. Удалит все документы из таблицы `documents`
3. Загрузит исправленные документы с корректной кодировкой
4. Сгенерирует новые embeddings

⚠️ **ВНИМАНИЕ:** Это удалит все существующие документы. Убедитесь, что backup создан!

### Шаг 3: Повышение порога similarity

После успешной миграции обновите `.env`:

```bash
SIMILARITY_THRESHOLD=0.7  # Было 0.35
```

И перезапустите бота.

---

## Опции скрипта

### `--execute`
Выполнить миграцию (по умолчанию dry-run)

```bash
python scripts/fix_encoding_migration.py --execute
```

### `--no-backup`
⛔ **ОПАСНО!** Пропустить создание backup

```bash
python scripts/fix_encoding_migration.py --execute --no-backup
```

---

## Стратегии исправления кодировки

Скрипт пытается следующие стратегии (в порядке приоритета):

1. **latin1 → utf-8** - Наиболее частая проблема (UTF-8 интерпретированный как Latin1)
2. **cp1251 → utf-8** - Windows Cyrillic кодировка
3. **windows-1251 → utf-8** - Альтернативное название cp1251
4. **iso-8859-5 → utf-8** - ISO Cyrillic кодировка

Если ни одна стратегия не сработала, документ остаётся без изменений.

---

## Валидация после миграции

### 1. Запустите тесты

```bash
pytest tests/test_rag_quality.py -v
```

**Ожидаемый результат:**
```
✅ test_valid_utf8_text PASSED
✅ test_search_knowledge_base_returns_valid_utf8 PASSED
✅ test_rag_agent_answer_quality PASSED
```

### 2. Проверьте quality вручную

```python
from core.vector_store import vector_store_manager

results = vector_store_manager.search_with_score(
    query="тестовый запрос",
    k=5,
    score_threshold=0.7
)

for doc in results:
    print(f"Score: {doc['score']:.2f} | {doc['content'][:100]}")
```

**Ожидаемый результат:**
- Текст отображается корректно (кириллица читаема)
- Score >= 0.7 для релевантных документов
- Нет символов типа "Ð", "â€™", "Ã"

### 3. Проверьте RAG agent

```bash
python app.py
```

Задайте вопрос:
```
> Найди информацию о проекте
```

**Ожидаемый результат:**
- Ответ содержит корректный русский текст
- Нет искажённых символов
- Релевантность ответа высокая

---

## Откат миграции (если что-то пошло не так)

### Вариант 1: Восстановление из backup

```python
import json
from core.vector_store import vector_store_manager

# Загрузить backup
with open('data/backups/documents_backup_20250124_143025.json', 'r', encoding='utf-8') as f:
    backup_docs = json.load(f)

# Восстановить документы
texts = [doc['content'] for doc in backup_docs]
metadatas = [doc['metadata'] for doc in backup_docs]

vector_store_manager.add_documents(texts, metadatas, validate_encoding=False)
```

### Вариант 2: Понизить порог обратно

Если миграция не помогла, верните старый порог:

```bash
SIMILARITY_THRESHOLD=0.35
```

---

## Предотвращение проблем в будущем

### Автоматическая валидация при загрузке

Теперь `vector_store_manager.add_documents()` **автоматически валидирует** кодировку:

```python
# Новое поведение (по умолчанию)
vector_store_manager.add_documents(
    texts=["Новый документ"],
    metadatas=[{"source": "manual"}],
    validate_encoding=True  # ← Включено по умолчанию
)
```

При обнаружении проблем:
- ✅ Автоматически пытается исправить
- ⚠️ Логирует предупреждение
- ❌ Выбрасывает `ValueError` если не может исправить

### Проверка перед загрузкой

```python
from core.vector_store import VectorStoreManager

# Валидация отдельного текста
validated, was_fixed = VectorStoreManager()._validate_and_fix_encoding(
    text="Ваш текст",
    doc_index=0
)

if was_fixed:
    print("⚠️ Кодировка была исправлена")
```

---

## FAQ

### Q: Сколько времени занимает миграция?
**A:** Зависит от количества документов:
- 100 документов: ~2-3 минуты
- 1000 документов: ~10-15 минут
- 10000 документов: ~1-2 часа

### Q: Безопасно ли удалять документы?
**A:** Да, при условии что:
1. Создан backup
2. Dry-run показал корректные исправления
3. У вас есть исходные документы где-то ещё

### Q: Что если миграция прервётся?
**A:** Используйте backup для восстановления. Скрипт создаёт backup **перед** удалением.

### Q: Можно ли запустить миграцию по частям?
**A:** Нет, скрипт обрабатывает все документы сразу. Для больших баз данных рассмотрите:
1. Экспорт документов в chunks
2. Миграция по частям вручную
3. Использование PostgreSQL COPY для bulk operations

### Q: Embeddings тоже обновятся?
**A:** Да! При загрузке исправленных документов генерируются новые embeddings на основе корректного текста.

---

## Дополнительные ресурсы

- [SUPABASE_SETUP_NOTES.md](SUPABASE_SETUP_NOTES.md) - Подробное описание проблемы
- [Encoding in Python](https://docs.python.org/3/howto/unicode.html) - Официальная документация
- [Common encoding issues](https://en.wikipedia.org/wiki/Mojibake) - Mojibake on Wikipedia

---

## Контакты для поддержки

Если возникли проблемы:
1. Проверьте logs в `logs/app.log`
2. Запустите тесты: `pytest tests/test_rag_quality.py`
3. Создайте issue с описанием проблемы и логами
