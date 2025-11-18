# Быстрый старт Webhook

## ✅ Webhook сервер УЖЕ ЗАПУЩЕН!

Сервер работает на: `http://localhost:8000`

## Тест локально

```bash
# В новом окне терминала:
cd D:\Eneca_AI_bot
.venv\Scripts\python.exe test_webhook.py
```

**Результат:** Агент отвечает "Привет! Готов помочь..."

## Запуск ngrok для публичного доступа

**В НОВОМ окне терминала (PowerShell или CMD):**

```bash
# Перейти в папку проекта
cd D:\Eneca_AI_bot

# Запустить ngrok
ngrok http 8000
```

**Скопируйте URL вида:** `https://xxxxx.ngrok-free.app`

## Настройка n8n

1. Открой workflow в n8n: https://eneca.app.n8n.cloud
2. Найди **HTTP Request** node или создай новый
3. Настрой:
   - **Method:** POST
   - **URL:** `https://YOUR-NGROK-URL.ngrok-free.app/webhook`
   - **Body → JSON:**
   ```json
   {
     "message": "{{ $json.message }}",
     "user_id": "{{ $json.user_id }}",
     "chat_id": "{{ $json.chat_id }}"
   }
   ```

4. Ответ вернется в формате:
   ```json
   {
     "response": "Ответ AI агента",
     "thread_id": "conversation-id",
     "success": true
   }
   ```

## Тест через n8n webhook

**Отправь POST на твой n8n webhook:**
```bash
curl -X POST https://eneca.app.n8n.cloud/webhook-test/0378ba55-d98b-4983-b0ef-83a0ac4ee28c \
  -H "Content-Type: application/json" \
  -d '{"message": "Привет! Тестирую AI бота"}'
```

n8n должен переслать это на наш ngrok URL, и вернуть ответ агента.

## Проверка статуса

**Веб интерфейс ngrok:**
Открой в браузере: http://localhost:4040

**Health check:**
```bash
curl http://localhost:8000/health
```

## Остановка

**Остановить webhook сервер:**
- Найти процесс: `tasklist | findstr python`
- Убить: `taskkill /F /PID <process_id>`

**Остановить ngrok:**
- В окне ngrok нажми `Ctrl+C`

## Логи

**Логи webhook сервера:**
- В реальном времени видны в окне где запущен `webhook_server.py`
- Файл: `logs/app.log`

**Логи ngrok:**
- Веб интерфейс: http://localhost:4040

## Готово!

Теперь твой enecawork может отправлять сообщения на AI агента через n8n webhook!
