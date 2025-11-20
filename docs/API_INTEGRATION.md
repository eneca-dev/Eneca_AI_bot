# Eneca AI Bot - API Integration Guide

Полное руководство по интеграции Eneca AI Bot в ваше приложение через REST API.

## Содержание

- [Быстрый старт](#быстрый-старт)
- [API Endpoints](#api-endpoints)
- [Аутентификация](#аутентификация)
- [Примеры интеграции](#примеры-интеграции)
- [Streaming ответы (SSE)](#streaming-ответы-sse)
- [Conversation Memory](#conversation-memory)
- [Обработка ошибок](#обработка-ошибок)

---

## Быстрый старт

### 1. Запуск сервера

```bash
# Активировать виртуальное окружение
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac

# Запустить API сервер
python server.py
```

Сервер запустится на `http://localhost:8000`

### 2. Настройка API Key (опционально)

Отредактируйте `.env` файл:

```bash
API_KEY=your_secure_api_key_here
API_KEY_HEADER=X-API-Key
```

**Важно:** Если `API_KEY` не установлен, аутентификация отключена (полезно для разработки).

### 3. Первый запрос

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_secure_api_key_here" \
  -d '{
    "message": "Привет! Кто ты?"
  }'
```

**Ответ:**
```json
{
  "response": "Привет! Я AI-ассистент Eneca...",
  "thread_id": "abc123-def456-...",
  "success": true
}
```

---

## API Endpoints

### 📍 POST /api/chat

Основной endpoint для отправки сообщений боту.

**Headers:**
```
Content-Type: application/json
X-API-Key: your_api_key  (если настроен)
```

**Request Body:**
```json
{
  "message": "Текст сообщения пользователя",
  "user_id": "optional-user-id",
  "chat_id": "optional-chat-id",
  "thread_id": "optional-thread-id",
  "metadata": {}
}
```

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `message` | string | ✅ Да | Текст сообщения пользователя |
| `user_id` | string | ❌ Нет | ID пользователя для аналитики |
| `chat_id` | string | ❌ Нет | ID чата (альтернатива thread_id) |
| `thread_id` | string | ❌ Нет | ID беседы для сохранения контекста |
| `metadata` | object | ❌ Нет | Дополнительные метаданные |

**Response:**
```json
{
  "response": "Ответ AI агента",
  "thread_id": "abc123-def456-...",
  "user_id": "optional-user-id",
  "chat_id": "optional-chat-id",
  "success": true
}
```

---

### 📍 POST /api/chat/stream

Streaming endpoint с Server-Sent Events (SSE) для получения ответа в реальном времени.

**Headers:**
```
Content-Type: application/json
X-API-Key: your_api_key  (если настроен)
```

**Request Body:**
```json
{
  "message": "Текст сообщения пользователя",
  "thread_id": "optional-thread-id"
}
```

**Response:** Server-Sent Events stream

События:
- `metadata` - метаданные беседы (thread_id)
- `chunk` - часть ответа
- `done` - завершение генерации
- `error` - ошибка

Пример событий:
```
data: {"type": "metadata", "thread_id": "abc123"}

data: {"type": "chunk", "content": "Привет!"}

data: {"type": "chunk", "content": "Как дела?"}

data: {"type": "done", "thread_id": "abc123"}
```

---

### 📍 GET /health

Проверка статуса сервера и агента.

**Response:**
```json
{
  "status": "healthy",
  "agent": {
    "initialized": true,
    "tools": 3,
    "memory_enabled": true
  }
}
```

---

### 📍 GET /

Базовая информация о сервере.

**Response:**
```json
{
  "status": "ok",
  "service": "Eneca AI Bot Webhook",
  "version": "1.0.0",
  "agent_loaded": true
}
```

---

## Аутентификация

### Настройка API Key

1. Сгенерируйте случайный API ключ:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

2. Добавьте в `.env`:
```bash
API_KEY=ваш_сгенерированный_ключ
```

3. Используйте в запросах:
```bash
curl -H "X-API-Key: ваш_ключ" ...
```

### Отключение аутентификации

Если `API_KEY` не установлен в `.env`, аутентификация отключена. Полезно для:
- Локальной разработки
- Тестирования
- Использования за защищенным reverse proxy

---

## Примеры интеграции

### 🔷 cURL

**Стандартный запрос:**
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_key" \
  -d '{
    "message": "Что такое LangChain?",
    "thread_id": "user-session-123"
  }'
```

**Streaming запрос:**
```bash
curl -X POST http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_key" \
  -d '{
    "message": "Расскажи о Python",
    "thread_id": "user-session-123"
  }'
```

---

### 🐍 Python

**Стандартный запрос:**
```python
import requests

API_URL = "http://localhost:8000/api/chat"
API_KEY = "your_api_key_here"

def send_message(message: str, thread_id: str = None):
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY
    }

    payload = {
        "message": message,
        "thread_id": thread_id
    }

    response = requests.post(API_URL, json=payload, headers=headers)
    return response.json()

# Использование
result = send_message("Привет!", thread_id="user-123")
print(result["response"])
print(f"Thread ID: {result['thread_id']}")
```

**Streaming запрос:**
```python
import requests
import json

API_URL = "http://localhost:8000/api/chat/stream"
API_KEY = "your_api_key_here"

def send_message_streaming(message: str, thread_id: str = None):
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY
    }

    payload = {
        "message": message,
        "thread_id": thread_id
    }

    response = requests.post(
        API_URL,
        json=payload,
        headers=headers,
        stream=True  # Важно!
    )

    for line in response.iter_lines():
        if line:
            line = line.decode('utf-8')
            if line.startswith('data: '):
                data = json.loads(line[6:])

                if data['type'] == 'metadata':
                    print(f"Thread ID: {data['thread_id']}")
                elif data['type'] == 'chunk':
                    print(data['content'], end=' ', flush=True)
                elif data['type'] == 'error':
                    print(f"\nError: {data['message']}")

# Использование
send_message_streaming("Расскажи о AI", thread_id="user-123")
```

---

### ⚛️ React (TypeScript)

Полный пример чат-компонента: [`docs/examples/react-chat.tsx`](examples/react-chat.tsx)

**Краткий пример:**
```tsx
const sendMessage = async (message: string) => {
  const response = await fetch('http://localhost:8000/api/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': 'your_key'
    },
    body: JSON.stringify({
      message,
      thread_id: threadId
    })
  });

  const data = await response.json();
  setThreadId(data.thread_id);
  return data.response;
};
```

---

### 🟨 Vanilla JavaScript

Полный пример HTML страницы: [`docs/examples/vanilla-chat.html`](examples/vanilla-chat.html)

**Краткий пример:**
```javascript
async function sendMessage(message) {
  const response = await fetch('http://localhost:8000/api/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': 'your_key'
    },
    body: JSON.stringify({
      message: message,
      thread_id: threadId
    })
  });

  const data = await response.json();
  threadId = data.thread_id;
  return data.response;
}
```

---

### 🌐 n8n Workflow

1. Добавьте **HTTP Request** node
2. Настройте:
   - **Method:** POST
   - **URL:** `http://localhost:8000/api/chat`
   - **Headers:**
     ```json
     {
       "X-API-Key": "your_key"
     }
     ```
   - **Body:**
     ```json
     {
       "message": "{{ $json.message }}",
       "user_id": "{{ $json.user_id }}",
       "thread_id": "{{ $json.thread_id }}"
     }
     ```

---

## Streaming ответы (SSE)

### Преимущества streaming

- ✅ Мгновенное отображение ответа (как ChatGPT)
- ✅ Улучшенный UX для длинных ответов
- ✅ Меньше perceived latency

### JavaScript EventSource API

```javascript
const eventSource = new EventSource(
  'http://localhost:8000/api/chat/stream?' +
  new URLSearchParams({
    message: 'Hello',
    thread_id: 'user-123'
  })
);

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);

  if (data.type === 'chunk') {
    console.log(data.content);
  } else if (data.type === 'done') {
    eventSource.close();
  }
};
```

**Примечание:** EventSource поддерживает только GET запросы. Для POST используйте Fetch API с `response.body.getReader()` (см. примеры выше).

---

## Conversation Memory

### Как работает memory

Каждая беседа сохраняется в SQLite базе данных (`data/checkpoints.db`) по уникальному `thread_id`.

### Управление thread_id

**1. Автоматическая генерация:**
```json
{
  "message": "Привет"
}
// Сервер вернет новый thread_id
```

**2. Явное указание:**
```json
{
  "message": "Продолжаем говорить о Python",
  "thread_id": "user-123-session-456"
}
```

**3. Использование chat_id:**
```json
{
  "message": "Hello",
  "chat_id": "telegram-chat-789"
}
// thread_id = chat_id
```

### Лучшие практики

✅ **Рекомендуется:**
- Сохраняйте `thread_id` на клиенте (localStorage, cookies)
- Используйте один `thread_id` для всей беседы
- Формат: `{platform}-{user_id}-{timestamp}`

❌ **Не рекомендуется:**
- Новый `thread_id` для каждого сообщения (потеря контекста)
- Слишком короткие ID (риск коллизий)

### Пример с localStorage (JavaScript)

```javascript
// Получить или создать thread_id
let threadId = localStorage.getItem('eneca_thread_id');
if (!threadId) {
  threadId = `web-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  localStorage.setItem('eneca_thread_id', threadId);
}

// Использовать в запросах
fetch('/webhook', {
  body: JSON.stringify({
    message: 'Hello',
    thread_id: threadId
  })
});
```

---

## Обработка ошибок

### Коды ошибок

| Код | Описание | Решение |
|-----|----------|---------|
| 401 | API key отсутствует | Добавьте header `X-API-Key` |
| 403 | Неверный API key | Проверьте ключ в `.env` |
| 422 | Некорректный запрос | Проверьте формат JSON |
| 500 | Внутренняя ошибка сервера | Проверьте логи `logs/app.log` |

### Пример обработки (JavaScript)

```javascript
try {
  const response = await fetch('/api/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': apiKey
    },
    body: JSON.stringify({ message })
  });

  if (!response.ok) {
    if (response.status === 401) {
      throw new Error('API key required');
    } else if (response.status === 403) {
      throw new Error('Invalid API key');
    } else {
      throw new Error(`HTTP error ${response.status}`);
    }
  }

  const data = await response.json();
  return data.response;

} catch (error) {
  console.error('API Error:', error);
  // Показать пользователю friendly error message
  return 'Произошла ошибка. Попробуйте еще раз.';
}
```

---

## Production Deployment

### 1. Настройка переменных окружения

```bash
# .env (production)
API_KEY=super_secure_random_key_here
OPENAI_API_KEY=your_openai_key
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_key
DEBUG=False
LOG_LEVEL=WARNING
ENVIRONMENT=production
```

### 2. Запуск с Uvicorn

```bash
uvicorn server:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 4 \
  --log-level warning
```

### 3. Systemd service (Linux)

Создайте `/etc/systemd/system/eneca-bot.service`:

```ini
[Unit]
Description=Eneca AI Bot Webhook Server
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/eneca_ai_bot
Environment="PATH=/opt/eneca_ai_bot/.venv/bin"
ExecStart=/opt/eneca_ai_bot/.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

Запустить:
```bash
sudo systemctl enable eneca-bot
sudo systemctl start eneca-bot
sudo systemctl status eneca-bot
```

### 4. Nginx Reverse Proxy

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location /api/chat {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        # Для streaming
        proxy_buffering off;
        proxy_cache off;
    }
}
```

### 5. HTTPS с Let's Encrypt

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

---

## Ограничения и Rate Limiting

**TODO:** Rate limiting будет добавлен в следующей версии.

Рекомендации на стороне клиента:
- Не более 10 запросов в минуту от одного пользователя
- Debounce пользовательского ввода (300-500ms)
- Показывать индикатор загрузки

---

## Логирование и мониторинг

### Логи

```bash
# Посмотреть логи
tail -f logs/app.log

# Фильтр по уровню
grep "ERROR" logs/app.log
grep "WARNING" logs/app.log
```

### Метрики

Endpoint `/health` можно использовать для мониторинга:

```bash
# Healthcheck скрипт
curl -f http://localhost:8000/health || exit 1
```

---

## FAQ

**Q: Нужен ли API key для локальной разработки?**
A: Нет, если `API_KEY` не установлен в `.env`, аутентификация отключена.

**Q: Как сбросить историю беседы?**
A: Используйте новый `thread_id` для каждой новой беседы.

**Q: Можно ли использовать WebSocket вместо SSE?**
A: Текущая версия поддерживает только SSE. WebSocket планируется в будущих версиях.

**Q: Поддерживается ли multimodal (изображения, файлы)?**
A: Пока нет, только текстовые сообщения.

---

## Поддержка

- 📧 Email: support@example.com
- 📖 Документация: [docs/](.)
- 🐛 Issues: GitHub Issues

---

## Лицензия

MIT License - см. LICENSE файл
