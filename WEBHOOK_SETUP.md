# Supabase Webhook Setup Guide

## ✅ Completed Implementation

Все необходимые изменения в коде выполнены:

- ✅ **DEV/PROD разделение:** RAG использует DEV проект, Chat использует PROD проект
- ✅ Обновлен `core/config.py` с разделением `supabase_rag_*` (DEV) и `supabase_chat_*` (PROD)
- ✅ Обновлен `core/vector_store.py` для использования DEV credentials
- ✅ Создан модуль `database/supabase_client.py` с SupabaseDBClient (PROD)
- ✅ Обновлен `app.py` с webhook endpoint `/webhook/supabase`
- ✅ Добавлена background task функция `process_webhook_message()`
- ✅ Реализована защита от бесконечного цикла (role filtering)

## 📋 Следующие шаги

### 1. Настроить DEV/PROD Supabase credentials в .env

⚠️ **КРИТИЧНО:** Теперь используется раздельная конфигурация для DEV и PROD проектов!

Откройте файл `.env` и настройте:

```bash
# DEV Supabase - для RAG (таблица documents)
SUPABASE_RAG_URL=https://mdybpekqfvwugqfvpdqa.supabase.co
SUPABASE_RAG_KEY=<ваш DEV anon key>

# PROD Supabase - для чата (таблица chat_messages)
SUPABASE_CHAT_URL=https://gvrcbvifirhxxdnvrwlz.supabase.co
SUPABASE_CHAT_SERVICE_KEY=<ваш PROD service_role key>
```

#### Где взять ключи:

**DEV проект (для RAG):**
1. Откройте https://mdybpekqfvwugqfvpdqa.supabase.co
2. Settings → API → **anon / public key**

**PROD проект (для чата):**
1. Откройте https://gvrcbvifirhxxdnvrwlz.supabase.co
2. Settings → API → **service_role key** (НЕ anon!)

⚠️ **ВАЖНО:**
- Не коммитьте `.env` в git!
- RAG использует DEV проект (только чтение)
- Chat использует PROD проект (запись через SERVICE_ROLE_KEY)
- Старые переменные `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_SERVICE_KEY` больше не используются

### 2. Локальное тестирование

#### Вариант A: Тест с PowerShell (Windows)

```powershell
# 1. Запустите бота
python app.py

# 2. В другом терминале запустите тест
.\test_webhook.ps1
```

#### Вариант B: Тест с curl

```bash
curl -X POST http://localhost:8000/webhook/supabase \
  -H "Content-Type: application/json" \
  -d '{
    "type": "INSERT",
    "table": "chat_messages",
    "schema": "public",
    "record": {
      "id": "test-123",
      "user_id": "test_user",
      "thread_id": "test_thread_1",
      "role": "user",
      "content": "Что такое Eneca?",
      "metadata": {}
    }
  }'
```

**Ожидаемый результат:**
- HTTP 200 OK с ответом: `{"status": "accepted", "message_id": "test-123"}`
- В логах (`logs/app.log`): Background processing started
- Если PROD credentials настроены: ответ записан в PROD Supabase

### 3. Настроить Webhook в Supabase Dashboard

⚠️ **ВАЖНО:** Webhook настраивается в **PROD проекте** (`gvrcbvifirhxxdnvrwlz`)!

1. Откройте https://supabase.com/dashboard
2. Выберите **PROD проект** `gvrcbvifirhxxdnvrwlz`
3. Перейдите: **Database** → **Webhooks**
4. Нажмите **"Create a new hook"** или **"Enable Webhooks"**

#### Параметры webhook:

| Параметр | Значение |
|----------|----------|
| **Name** | `AI Bot - New User Message` |
| **Table** | `public.chat_messages` |
| **Events** | ✅ INSERT (остальные выключить) |
| **HTTP Method** | POST |
| **URL** | `https://ai-bot.eneca.work/webhook/supabase` |
| **Headers** | `Content-Type: application/json` |
| **Filter** | `role eq user` ⚠️ **КРИТИЧНО!** |

⚠️ **ВАЖНО:** Фильтр `role eq user` предотвращает бесконечный цикл!

5. Нажмите **"Enable"** или **"Save"**

### 4. Production Deployment

```bash
# 1. Обновите .env на сервере с DEV/PROD credentials
# 2. Пересоберите Docker
docker-compose up -d --build

# 3. Проверьте логи
docker-compose logs -f ai_agent

# 4. Проверьте что endpoint доступен
curl https://ai-bot.eneca.work/webhook/supabase
```

### 5. End-to-End Testing

Вставьте тестовое сообщение в **PROD Supabase**:

```sql
-- В PROD Supabase SQL Editor (gvrcbvifirhxxdnvrwlz)
INSERT INTO chat_messages (user_id, thread_id, role, content)
VALUES ('test_user', 'e2e_test', 'user', 'Расскажи о компании Eneca');

-- Подождите 10-15 секунд

-- Проверьте ответ
SELECT role, content, created_at
FROM chat_messages
WHERE thread_id = 'e2e_test'
ORDER BY created_at DESC;

-- Ожидается: 2 строки (user + assistant)
```

### 6. Проверка на бесконечный цикл

```sql
-- Проверьте количество сообщений по ролям
SELECT role, COUNT(*) as count
FROM chat_messages
WHERE thread_id = 'e2e_test'
GROUP BY role;

-- Ожидается: Одинаковое количество user и assistant
-- Если assistant >> user - есть проблема с циклом!
```

## 🔧 Troubleshooting

### Webhook не срабатывает

1. Проверьте логи Supabase: Database → Webhooks → кликните на webhook → View Logs
2. Проверьте фильтр: `role eq user` должен быть установлен
3. Проверьте URL: `https://ai-bot.eneca.work/webhook/supabase`

### Бот не отвечает

1. Проверьте логи: `docker-compose logs -f ai_agent`
2. Проверьте PROD credentials в .env (`SUPABASE_CHAT_URL`, `SUPABASE_CHAT_SERVICE_KEY`)
3. Проверьте что Supabase DB client инициализирован: смотрите в логах "Supabase DB Client initialized with PROD SERVICE_ROLE_KEY"

### Бесконечный цикл сообщений

1. **Немедленно отключите webhook** в Supabase Dashboard
2. Проверьте фильтр `role eq user` в конфигурации webhook
3. Проверьте код в `app.py:193` - там должен быть check на role

### Ошибки в логах

```
Failed to write response to database
```
→ Проверьте PROD credentials: `SUPABASE_CHAT_URL` и `SUPABASE_CHAT_SERVICE_KEY`

```
Supabase DB client not available
```
→ Проверьте что в .env заполнены `SUPABASE_CHAT_URL` и `SUPABASE_CHAT_SERVICE_KEY`

```
Vector store not initialized
```
→ Проверьте DEV credentials: `SUPABASE_RAG_URL` и `SUPABASE_RAG_KEY`

## 📊 Мониторинг

### Просмотр логов

```bash
# Все логи
tail -f logs/app.log

# Только webhook события
tail -f logs/app.log | grep "Webhook"

# Только background tasks
tail -f logs/app.log | grep "Background"
```

### Проверка работы

```bash
# Проверить что endpoint доступен
curl https://ai-bot.eneca.work/webhook/supabase

# Проверить health (если добавлен endpoint)
curl https://ai-bot.eneca.work/health
```

## 🎉 Успешная интеграция

Если все работает, вы должны видеть:

1. ✅ Webhook в Supabase показывает успешные доставки
2. ✅ В логах: "Webhook received for thread: ..."
3. ✅ В логах: "Background processing started..."
4. ✅ В логах: "Response written to database..."
5. ✅ В Supabase таблице `chat_messages`: появляются ответы бота с role='assistant'

## 📚 Дополнительные ресурсы

- [План реализации](C:\Users\ADMIN\.claude\plans\expressive-coalescing-firefly.md)
- [Supabase Database Webhooks Docs](https://supabase.com/docs/guides/database/webhooks)
- [FastAPI BackgroundTasks](https://fastapi.tiangolo.com/tutorial/background-tasks/)
