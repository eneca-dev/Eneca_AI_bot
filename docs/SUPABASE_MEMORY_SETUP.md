## Supabase Memory для Conversation Persistence

### Обзор

Supabase Memory позволяет хранить историю разговоров в PostgreSQL через Supabase, используя существующую таблицу `n8n_chat_histories`. Это обеспечивает:

- ✅ **Персистентность** - история сохраняется между перезапусками
- ✅ **Масштабируемость** - несколько инстансов бота могут использовать одну БД
- ✅ **Совместимость с n8n** - использует ту же таблицу, что и n8n workflows
- ✅ **Production-ready** - надёжное PostgreSQL хранилище

---

## Сравнение Backend'ов для памяти

| Backend | Персистентность | Масштабируемость | Производительность | Use Case |
|---------|----------------|------------------|-------------------|----------|
| **InMemory** | ❌ Нет | ❌ Нет | ⚡ Очень быстро | Development, тестирование |
| **SQLite** | ✅ Да | ❌ Single instance | ⚡ Быстро | Production (1 instance) |
| **Supabase** | ✅ Да | ✅ Multi-instance | 🔥 Средне | **Production (multi-instance)** |

**Рекомендация:** Используйте **Supabase** для production deployment с несколькими инстансами или интеграцией с n8n.

---

## Настройка

### Шаг 1: Проверка таблицы в Supabase

Таблица `n8n_chat_histories` должна существовать в вашей Supabase базе данных.

**Типичная схема:**

```sql
CREATE TABLE n8n_chat_histories (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    message_type TEXT NOT NULL,  -- 'ai', 'human', 'checkpoint'
    message TEXT NOT NULL,        -- JSON для checkpoints
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB
);

-- Индексы для быстрого поиска
CREATE INDEX idx_chat_histories_session_id ON n8n_chat_histories(session_id);
CREATE INDEX idx_chat_histories_created_at ON n8n_chat_histories(created_at DESC);
CREATE INDEX idx_chat_histories_message_type ON n8n_chat_histories(message_type);
```

**Если таблицы нет**, создайте её через Supabase SQL Editor:

1. Откройте Supabase Dashboard → SQL Editor
2. Вставьте SQL выше
3. Нажмите "Run"

### Шаг 2: Конфигурация `.env`

Обновите `.env` файл:

```bash
# Memory Configuration
ENABLE_CONVERSATION_MEMORY=true
MEMORY_TYPE=supabase  # ← Изменить на supabase

# Supabase Memory Configuration
MEMORY_SUPABASE_TABLE=n8n_chat_histories

# Supabase Connection (уже должно быть настроено)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_anon_key
```

⚠️ **Важно:** Используйте `service_role` key если нужны полные права для записи/удаления.

### Шаг 3: Верификация

Проверьте что всё работает:

```bash
# Проверка подключения и таблицы
python scripts/verify_supabase_memory.py

# Полная проверка с тестами записи/чтения
python scripts/verify_supabase_memory.py --test
```

**Ожидаемый вывод:**

```
============================================================
ПРОВЕРКА ПОДКЛЮЧЕНИЯ К SUPABASE
============================================================
✅ Supabase подключён
URL: https://your-project.supabase.co...

============================================================
ПРОВЕРКА ТАБЛИЦЫ: n8n_chat_histories
============================================================
✅ Таблица n8n_chat_histories существует
📊 Таблица содержит данные (минимум 1 запись)

============================================================
ПРОВЕРКА СХЕМЫ ТАБЛИЦЫ
============================================================
Найденные колонки:
  ✓ id: Primary key
  ✓ session_id: Thread/conversation ID
  ✓ message_type: Type: ai, human, or checkpoint
  ✓ message: Message content or checkpoint data
  ✓ created_at: Timestamp
  ✓ metadata: JSONB metadata (optional)

✅ Все ожидаемые колонки присутствуют

============================================================
✅ ВЕРИФИКАЦИЯ ЗАВЕРШЕНА УСПЕШНО
============================================================
```

### Шаг 4: Запуск бота

Запустите бот с Supabase memory:

```bash
python app.py
```

История разговоров теперь сохраняется в Supabase! 🎉

---

## Использование

### В коде

```python
from agents.orchestrator import OrchestratorAgent

orchestrator = OrchestratorAgent()

# Разговор с пользователем user_123
response = orchestrator.process_message(
    user_message="Привет!",
    thread_id="user_123"  # ← session_id в Supabase
)

# Все сообщения для user_123 сохраняются
```

### Thread ID / Session ID

`thread_id` в коде = `session_id` в Supabase таблице.

**Рекомендации по thread_id:**
- Используйте user ID: `user_{telegram_id}`
- Или UUID для уникальных сессий: `session_{uuid}`
- Или комбинацию: `{platform}_{user_id}` (например: `telegram_12345`)

---

## Архитектура

### Как это работает

```
User Message
    ↓
OrchestratorAgent.process_message(message, thread_id="user_123")
    ↓
LangGraph ReAct Agent
    ↓
SupabaseCheckpointer.put(checkpoint_data)
    ↓
Supabase n8n_chat_histories table
    INSERT INTO n8n_chat_histories (
        session_id='user_123',
        message_type='checkpoint',
        message='{"messages": [...], "state": {...}}',
        created_at=NOW(),
        metadata='{...}'
    )
```

### Хранение в таблице

**Типы записей:**

1. **checkpoint** - полное состояние разговора (LangGraph checkpoints)
   ```json
   {
     "session_id": "user_123",
     "message_type": "checkpoint",
     "message": "{\"checkpoint\": {...}, \"metadata\": {...}}",
     "created_at": "2025-01-24T12:00:00Z"
   }
   ```

2. **human** / **ai** - отдельные сообщения (n8n format, опционально)
   ```json
   {
     "session_id": "user_123",
     "message_type": "human",
     "message": "Привет!",
     "created_at": "2025-01-24T12:00:00Z"
   }
   ```

**Custom Checkpointer** (`core/supabase_checkpointer.py`) автоматически:
- Сериализует checkpoint data в JSON
- Сохраняет в `message` колонку
- Помечает `message_type='checkpoint'`
- Сохраняет `metadata` отдельно

---

## Примеры

### Пример 1: Простой разговор

```python
from agents.orchestrator import OrchestratorAgent

orchestrator = OrchestratorAgent()
thread_id = "telegram_user_12345"

# Первое сообщение
response1 = orchestrator.process_message("Привет!", thread_id=thread_id)
print(response1)  # "Здравствуйте! Чем могу помочь?"

# Второе сообщение (с контекстом первого)
response2 = orchestrator.process_message("Расскажи о проекте", thread_id=thread_id)
print(response2)  # Ответ с учётом истории
```

### Пример 2: Просмотр истории

```python
from core.vector_store import vector_store_manager
from core.supabase_checkpointer import SupabaseCheckpointer

checkpointer = SupabaseCheckpointer(
    supabase_client=vector_store_manager.supabase_client,
    table_name="n8n_chat_histories"
)

# Получить историю разговора
history = checkpointer.get_conversation_history(
    thread_id="telegram_user_12345",
    limit=50
)

for msg in history:
    print(f"[{msg['type']}] {msg['content']}")
```

### Пример 3: Очистка истории

```python
from core.memory import memory_manager

# Удалить всю историю для пользователя
checkpointer = memory_manager.checkpointer
checkpointer.delete_thread("telegram_user_12345")
```

---

## Мониторинг и обслуживание

### Просмотр данных в Supabase

**SQL запросы для мониторинга:**

```sql
-- Количество записей по типам
SELECT message_type, COUNT(*) as count
FROM n8n_chat_histories
GROUP BY message_type;

-- Активные сессии за последний час
SELECT session_id, COUNT(*) as messages
FROM n8n_chat_histories
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY session_id
ORDER BY messages DESC;

-- Размер данных
SELECT
    pg_size_pretty(pg_total_relation_size('n8n_chat_histories')) as total_size;

-- Последние разговоры
SELECT session_id, message_type, LEFT(message, 100), created_at
FROM n8n_chat_histories
ORDER BY created_at DESC
LIMIT 20;
```

### Очистка старых данных

**Автоматическая очистка** (через Supabase SQL Editor):

```sql
-- Удалить записи старше 30 дней
DELETE FROM n8n_chat_histories
WHERE created_at < NOW() - INTERVAL '30 days';

-- Или создать scheduled job (Supabase Database Webhooks)
CREATE OR REPLACE FUNCTION cleanup_old_chat_histories()
RETURNS void AS $$
BEGIN
    DELETE FROM n8n_chat_histories
    WHERE created_at < NOW() - INTERVAL '30 days';
END;
$$ LANGUAGE plpgsql;

-- Запускать каждый день в 2:00 AM (настроить через pg_cron)
```

---

## Troubleshooting

### Проблема: "Table n8n_chat_histories does not exist"

**Решение:**
1. Создайте таблицу (см. Шаг 1 выше)
2. Или измените имя таблицы в `.env`: `MEMORY_SUPABASE_TABLE=your_table_name`

### Проблема: "Permission denied for table n8n_chat_histories"

**Решение:**
1. Используйте `service_role` key вместо `anon` key
2. Или настройте Row Level Security (RLS) в Supabase:
   ```sql
   ALTER TABLE n8n_chat_histories ENABLE ROW LEVEL SECURITY;

   CREATE POLICY "Allow anon key access"
   ON n8n_chat_histories
   FOR ALL
   USING (true);
   ```

### Проблема: Checkpoint не сохраняется

**Диагностика:**

```bash
# Запустить тест
python scripts/verify_supabase_memory.py --test

# Проверить логи
tail -f logs/app.log | grep -i checkpoint
```

**Возможные причины:**
- Неправильный формат checkpoint data
- Ошибка serialization в JSON
- Ограничения на размер TEXT колонки

### Проблема: Медленная работа

**Оптимизация:**

```sql
-- Добавить индексы
CREATE INDEX IF NOT EXISTS idx_chat_session_created
ON n8n_chat_histories(session_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_chat_type_session
ON n8n_chat_histories(message_type, session_id);

-- Анализ производительности
EXPLAIN ANALYZE
SELECT * FROM n8n_chat_histories
WHERE session_id = 'user_123'
ORDER BY created_at DESC
LIMIT 10;
```

---

## Миграция

### Из InMemory/SQLite в Supabase

1. **Остановить бот**
2. **Обновить `.env`:**
   ```bash
   MEMORY_TYPE=supabase
   ```
3. **Запустить бот**

⚠️ **Важно:** История из InMemory/SQLite **не переносится** автоматически. Разговоры начнутся с чистого листа.

### Из Supabase обратно в SQLite

```bash
MEMORY_TYPE=sqlite
```

Данные в Supabase остаются и могут быть восстановлены при возврате к `MEMORY_TYPE=supabase`.

---

## FAQ

### Q: Можно ли использовать Supabase memory без n8n?

**A:** Да! Таблица `n8n_chat_histories` может использоваться без n8n workflows. Просто создайте таблицу с нужной схемой.

### Q: Какой размер checkpoint data?

**A:** Обычно 2-10 KB на checkpoint (зависит от длины разговора). Для 1000 пользователей с 10 сообщениями каждый ≈ 20-100 MB.

### Q: Как часто создаются checkpoints?

**A:** Checkpoint создаётся **после каждого сообщения** пользователя (когда orchestrator заканчивает обработку).

### Q: Можно ли использовать другую таблицу?

**A:** Да, установите `MEMORY_SUPABASE_TABLE=your_custom_table` в `.env`. Убедитесь что схема совместима.

### Q: Как работает с несколькими инстансами бота?

**A:** Отлично! Все инстансы используют одну таблицу Supabase, поэтому history синхронизирована автоматически.

---

## Дополнительные ресурсы

- [LangGraph Checkpointers](https://langchain-ai.github.io/langgraph/how-tos/persistence/)
- [Supabase PostgreSQL Docs](https://supabase.com/docs/guides/database)
- [n8n Chat Memory](https://docs.n8n.io/integrations/builtin/cluster-nodes/sub-nodes/n8n-nodes-langchain.memorybufferchat/)

---

## Контакты

Если возникли проблемы:
1. Проверьте логи: `logs/app.log`
2. Запустите диагностику: `python scripts/verify_supabase_memory.py --test`
3. Проверьте Supabase Dashboard → Table Editor → n8n_chat_histories
