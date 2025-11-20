# Eneca AI Bot - Webhook Integration

> 📚 **Полное руководство по интеграции:** См. [API_INTEGRATION.md](API_INTEGRATION.md)
>
> 🚀 **Новые возможности:**
> - ✅ API Key аутентификация
> - ✅ Streaming ответы (Server-Sent Events)
> - ✅ Примеры для React и vanilla JavaScript
> - ✅ Conversation memory

## Локальное тестирование с ngrok

### 1. Запуск API сервера

```bash
# Активировать виртуальное окружение
.venv\Scripts\activate

# Запустить сервер
python server.py
```

Сервер запустится на `http://localhost:8000`

### 2. Установка ngrok (если еще не установлен)

**Скачать:**
- https://ngrok.com/download
- Или через winget: `winget install ngrok`

**Настройка:**
```bash
# Зарегистрироваться на ngrok.com и получить authtoken
ngrok config add-authtoken YOUR_AUTH_TOKEN
```

### 3. Запуск ngrok туннеля

```bash
ngrok http 8000
```

Вы получите публичный URL вида:
```
https://abc123.ngrok-free.app
```

### 4. Настройка n8n

В n8n workflow:
1. Добавить **HTTP Request** node
2. URL: `https://YOUR-NGROK-URL.ngrok-free.app/api/chat`
3. Method: `POST`
4. Body (JSON):
```json
{
  "message": "{{ $json.message }}",
  "user_id": "{{ $json.user_id }}",
  "chat_id": "{{ $json.chat_id }}"
}
```

### 5. Тестирование

**Локальный тест (без ngrok):**
```bash
python test_webhook.py
```

**Через curl:**
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"Привет!\"}"
```

**Через ngrok URL:**
```bash
curl -X POST https://YOUR-NGROK-URL.ngrok-free.app/api/chat \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"Привет!\"}"
```

## API Endpoints

### POST /api/chat
Основной endpoint для обработки сообщений

**Request:**
```json
{
  "message": "Текст сообщения пользователя",
  "user_id": "optional-user-id",
  "chat_id": "optional-chat-id",
  "thread_id": "optional-thread-id",
  "metadata": {}
}
```

**Response:**
```json
{
  "response": "Ответ агента",
  "thread_id": "conversation-thread-id",
  "user_id": "optional-user-id",
  "chat_id": "optional-chat-id",
  "success": true
}
```

### POST /api/chat/stream
Streaming endpoint с Server-Sent Events (SSE)

### POST /api/debug
Отладочный endpoint - принимает любой JSON

### GET /health
Проверка статуса сервера

### GET /
Базовая информация о сервере

## Особенности

### Conversation Memory
- Каждый `thread_id` или `chat_id` создает отдельную беседу
- Агент запоминает контекст в рамках одного thread
- История сохраняется в SQLite (`data/checkpoints.db`)

### Автоматический thread_id
Если не передан `thread_id` или `chat_id`, генерируется автоматически

### Логирование
Все запросы логируются в `logs/app.log`

## Production Deployment (VPS)

Когда будете деплоить на VPS:

1. **Установить зависимости:**
```bash
pip install -r requirements.txt
```

2. **Настроить .env файл**

3. **Запустить с systemd или supervisor:**
```bash
uvicorn server:app --host 0.0.0.0 --port 8000
```

4. **Nginx reverse proxy:**
```nginx
location /ai-webhook {
    proxy_pass http://localhost:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

5. **Обновить n8n webhook URL** на production URL
