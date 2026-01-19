# Analytics Agent - Quick Start Guide

**⚠️ ВАЖНО:** Analytics Agent - это **standalone сервис**, который работает НЕЗАВИСИМО от chat/orchestrator.

## Архитектура
```
Frontend AI Dashboard
    ↓
POST /api/analytics  ← Analytics Agent (этот сервис)

Frontend Chat
    ↓
POST /api/chat  ← Orchestrator → MCPAgent/RAGAgent
```

Analytics НЕ доступен через chat. Только через прямой API endpoint.

---

## 🚀 Быстрый старт за 5 минут

### 1. Установка (если еще не сделано)
```bash
# Активируйте виртуальное окружение
.venv\Scripts\activate  # Windows
# или
source .venv/bin/activate  # Linux/Mac

# Все зависимости уже в requirements.txt
pip install -r requirements.txt
```

### 2. Запуск сервера
```bash
python server.py
```

Сервер запустится на `http://localhost:8000`

### 3. Проверка работоспособности
```bash
# Health check
curl http://localhost:8000/health

# Должен вернуть информацию об агентах
```

### 4. Тестовый запрос
```bash
curl -X POST http://localhost:8000/api/analytics \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Статистика проектов",
    "user_role": "admin"
  }'
```

**Ожидаемый ответ:**
```json
{
    "type": "text",
    "content": "📊 Статистика:\n\nВсего проектов: 2\n✅ Активных: 1\n✅ Завершенных: 1",
    "sql_query": "SELECT COUNT(*) as total_projects FROM projects",
    "metadata": {"row_count": 2},
    "success": true
}
```

## 📊 Примеры запросов

### Пример 1: График распределения (Pie Chart)
```bash
curl -X POST http://localhost:8000/api/analytics \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Покажи количество проектов по статусам",
    "user_role": "manager"
  }'
```

**Ответ:**
```json
{
    "type": "chart",
    "content": [
        {"label": "active", "value": 15},
        {"label": "completed", "value": 8}
    ],
    "chart_config": {
        "type": "pie",
        "data": {
            "labels": ["active", "completed"],
            "datasets": [{
                "data": [15, 8],
                "backgroundColor": ["#36A2EB", "#4BC0C0"]
            }]
        }
    }
}
```

### Пример 2: Сравнение (Bar Chart)
```bash
curl -X POST http://localhost:8000/api/analytics \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Сравни прогресс всех проектов",
    "user_role": "admin"
  }'
```

### Пример 3: Таблица данных
```bash
curl -X POST http://localhost:8000/api/analytics \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Покажи список проектов с прогрессом",
    "user_role": "manager"
  }'
```

## 🎨 Frontend Integration

### HTML + JavaScript (Vanilla)
```html
<!DOCTYPE html>
<html>
<head>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
    <canvas id="myChart"></canvas>

    <script>
        async function fetchAnalytics(query) {
            const response = await fetch('http://localhost:8000/api/analytics', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query, user_role: 'admin' })
            });

            const data = await response.json();

            if (data.type === 'chart') {
                const ctx = document.getElementById('myChart');
                new Chart(ctx, data.chart_config);
            }
        }

        // Использование
        fetchAnalytics('Покажи проекты по статусам');
    </script>
</body>
</html>
```

### React
```jsx
import { useState } from 'react';
import { Pie, Bar } from 'react-chartjs-2';

function Analytics() {
    const [result, setResult] = useState(null);

    const fetchAnalytics = async (query) => {
        const res = await fetch('/api/analytics', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, user_role: 'admin' })
        });
        setResult(await res.json());
    };

    return (
        <div>
            <input
                type="text"
                placeholder="Введите запрос..."
                onKeyPress={(e) => {
                    if (e.key === 'Enter') fetchAnalytics(e.target.value);
                }}
            />

            {result?.type === 'chart' && result.chart_config.type === 'pie' && (
                <Pie data={result.chart_config.data} />
            )}

            {result?.type === 'chart' && result.chart_config.type === 'bar' && (
                <Bar data={result.chart_config.data} />
            )}

            {result?.type === 'text' && (
                <p style={{whiteSpace: 'pre-wrap'}}>{result.content}</p>
            )}
        </div>
    );
}
```

### Vue 3
```vue
<template>
    <div>
        <input
            v-model="query"
            @keyup.enter="fetch"
            placeholder="Введите запрос..."
        />

        <Pie v-if="result?.type === 'chart'"
             :data="result.chart_config.data" />

        <p v-if="result?.type === 'text'" style="white-space: pre-wrap">
            {{ result.content }}
        </p>
    </div>
</template>

<script setup>
import { ref } from 'vue';
import { Pie } from 'vue-chartjs';

const query = ref('');
const result = ref(null);

const fetch = async () => {
    const res = await fetch('/api/analytics', {
        method: 'POST',
        body: JSON.stringify({ query: query.value, user_role: 'admin' })
    });
    result.value = await res.json();
};
</script>
```

## 🧪 Тестирование

### Запуск unit tests
```bash
pytest tests/test_analytics_basic.py -v
```

### Запуск с coverage
```bash
pytest tests/test_analytics_basic.py --cov=agents.analytics_agent
```

### Интерактивное тестирование
```bash
# Запустите Python REPL
python

# В REPL:
from agents.analytics_agent import AnalyticsAgent

agent = AnalyticsAgent()
result = agent.process_analytics("Статистика проектов", user_role="admin")
print(result.model_dump_json(indent=2))
```

## 🔧 Настройка

### API Key (опционально)
Если хотите защитить endpoint:

1. В `.env` добавьте:
```bash
API_KEY=your_secure_random_key_here
API_KEY_HEADER=X-API-Key
```

2. При запросах добавляйте заголовок:
```bash
curl -X POST http://localhost:8000/api/analytics \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_secure_random_key_here" \
  -d '{"query": "..."}'
```

### RBAC Roles
Доступные роли:
- `admin` (100) - полный доступ
- `manager` (50) - большинство данных
- `engineer` (30) - ограниченный доступ
- `viewer` (10) - только чтение
- `guest` (0) - минимальный доступ

## 📝 Поддерживаемые типы запросов

### ✅ Статистика
- "Сколько проектов в системе?"
- "Количество активных объектов"
- "Средний прогресс по этапам"

### ✅ Графики
- "Покажи график проектов по статусам"
- "Диаграмма распределения задач"
- "График прогресса всех проектов"

### ✅ Таблицы
- "Список всех проектов с прогрессом"
- "Топ-10 самых активных сотрудников"
- "Сравни все проекты"

### ✅ Временные тренды
- "Динамика создания проектов за месяц"
- "График завершенных задач по дням"
- "Изменение прогресса за неделю"

## ⚠️ Важные замечания

### Mock Data
**ВАЖНО:** Сейчас используются **тестовые данные** (mock). Для production нужно:

1. Подключить реальное выполнение SQL через Supabase RPC или psycopg2
2. Создать Postgres функцию для безопасного выполнения SELECT
3. Настроить индексы для производительности

См. [Production Setup](docs/ANALYTICS_SETUP_SUMMARY.md#что-нужно-доработать-для-production)

### SQL Security
Агент генерирует **только SELECT** запросы. INSERT/UPDATE/DELETE запрещены на уровне кода.

### Performance
Для больших выборок рекомендуется:
- Добавить LIMIT в запросы
- Использовать кэширование (Redis)
- Создать индексы на часто используемых колонках

## 📚 Дополнительная документация

- **Полная документация:** [docs/ANALYTICS_AGENT.md](docs/ANALYTICS_AGENT.md)
- **Setup Summary:** [docs/ANALYTICS_SETUP_SUMMARY.md](docs/ANALYTICS_SETUP_SUMMARY.md)
- **System Prompt:** [prompts/analytics_agent.md](prompts/analytics_agent.md)
- **Source Code:** [agents/analytics_agent.py](agents/analytics_agent.py)

## 🐛 Troubleshooting

### Ошибка: "Module not found: agents.analytics_agent"
**Решение:** Убедитесь, что запускаете сервер из корня проекта:
```bash
cd d:/Eneca_AI_bot
python server.py
```

### Ошибка: "OPENAI_API_KEY not found"
**Решение:** Проверьте `.env` файл:
```bash
OPENAI_API_KEY=sk-...your-key-here...
```

### Endpoint не отвечает
**Решение:** Проверьте, что сервер запущен:
```bash
# В другом терминале
curl http://localhost:8000/health
```

### Chart не отображается на фронте
**Решение:** Убедитесь, что:
1. Установлен Chart.js: `npm install chart.js`
2. Зарегистрированы нужные компоненты (ArcElement, BarElement и т.д.)
3. Правильно передаете `data` и `options`

## 💡 Tips & Tricks

### Tip 1: Используйте конкретные запросы
❌ Плохо: "Покажи данные"
✅ Хорошо: "Покажи количество активных проектов за последний месяц"

### Tip 2: Указывайте тип визуализации
❌ "Статистика проектов" → может вернуть текст
✅ "График проектов по статусам" → вернет chart config

### Tip 3: Используйте правильную роль
Для тестирования используйте `user_role: "admin"` - получите полный доступ к данным.

### Tip 4: Проверяйте SQL query
В ответе всегда есть `sql_query` - проверяйте его для понимания, что именно выполнилось.

---

**Happy Analytics! 📊**

Если нужна помощь - смотрите [полную документацию](docs/ANALYTICS_AGENT.md) или пишите в Issues.
