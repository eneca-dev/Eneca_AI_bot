# Analytics Agent Documentation

## Обзор

Analytics Agent — **standalone сервис** для аналитики данных, генерации отчетов и визуализации в системе Eneca AI Bot.

**⚠️ ВАЖНО:** Analytics Agent работает **независимо** от Orchestrator Agent:
- НЕ зарегистрирован в `config/agents.yaml`
- НЕ доступен через `/api/chat` endpoint
- Имеет собственный endpoint `/api/analytics`
- Предназначен для AI Dashboard, а не для chat-интерфейса

## Возможности

### 1. SQL Query Generation
- Автоматическая генерация SQL-запросов из естественного языка
- Безопасные SELECT-запросы с параметризацией
- Поддержка JOIN, GROUP BY, агрегатных функций

### 2. Data Analysis
- Статистический анализ (COUNT, AVG, SUM, MIN, MAX)
- Временные тренды и динамика
- Распределение по категориям
- Сравнительный анализ

### 3. Visualization
- Подготовка данных для Chart.js
- Типы графиков: pie, bar, line, table
- Готовые конфигурации для фронтенда

### 4. Report Generation
- Текстовые отчеты с инсайтами
- Структурированные таблицы
- Резюме ключевых метрик

### 5. RBAC Integration
- Учет ролей пользователей
- Ограничение доступа к данным
- Агрегация для низких ролей

## API Endpoint

### POST /api/analytics

**URL:** `http://localhost:8000/api/analytics`

**Headers:**
```
Content-Type: application/json
X-API-Key: your_api_key_here  (если настроено в .env)
```

**Request Body:**
```json
{
    "query": "Покажи количество проектов по статусам",
    "user_id": "uuid-user-id",  // optional
    "user_role": "manager",      // optional (автоматически загружается из БД)
    "metadata": {}               // optional
}
```

**Response:**
```json
{
    "type": "chart",  // "text", "table", "chart", "mixed"
    "content": [
        {"label": "active", "value": 15},
        {"label": "completed", "value": 8}
    ],
    "sql_query": "SELECT status, COUNT(*) FROM projects GROUP BY status",
    "chart_config": {
        "type": "pie",
        "data": {
            "labels": ["active", "completed"],
            "datasets": [{
                "data": [15, 8],
                "backgroundColor": ["#36A2EB", "#4BC0C0"]
            }]
        },
        "options": {
            "responsive": true,
            "plugins": {"legend": {"position": "bottom"}}
        }
    },
    "metadata": {
        "row_count": 2,
        "execution_time": 0.123
    },
    "success": true,
    "error": null
}
```

## Примеры Запросов

### 1. Статистика проектов (Pie Chart)

**Request:**
```bash
curl -X POST http://localhost:8000/api/analytics \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{
    "query": "Покажи количество проектов по статусам",
    "user_role": "manager"
  }'
```

**Response:**
- `type`: "chart"
- `chart_config.type`: "pie"
- Содержит готовую конфигурацию для Chart.js

**Frontend Integration (React/Vue):**
```javascript
// Использование с Chart.js
import { Pie } from 'react-chartjs-2';

const response = await fetch('/api/analytics', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query: 'Покажи статистику проектов' })
});

const data = await response.json();

if (data.type === 'chart') {
    <Pie data={data.chart_config.data} options={data.chart_config.options} />
}
```

### 2. Прогресс проектов (Bar Chart)

**Request:**
```bash
curl -X POST http://localhost:8000/api/analytics \
  -H "Content-Type: application/json" \
  -d '{
    "query": "График прогресса всех активных проектов",
    "user_id": "user-uuid"
  }'
```

**Response:**
- `type`: "chart"
- `chart_config.type`: "bar"
- Данные отсортированы по прогрессу

### 3. Статистика за период (Text Report)

**Request:**
```bash
curl -X POST http://localhost:8000/api/analytics \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Статистика завершенных объектов за последний месяц",
    "user_role": "admin"
  }'
```

**Response:**
```json
{
    "type": "text",
    "content": "📊 Статистика за последний месяц:\n\n✅ Завершено объектов: 42\n👥 Уникальных исполнителей: 12\n📈 Средний прогресс: 95%",
    "sql_query": "SELECT COUNT(*) ...",
    "metadata": {
        "row_count": 1
    },
    "success": true
}
```

### 4. Сравнительная таблица (Table)

**Request:**
```bash
curl -X POST http://localhost:8000/api/analytics \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Сравни прогресс всех проектов",
    "user_role": "manager"
  }'
```

**Response:**
```json
{
    "type": "table",
    "content": [
        {
            "project_name": "Проект А",
            "status": "active",
            "stages_count": 5,
            "avg_progress": 75.5
        },
        {
            "project_name": "Проект Б",
            "status": "completed",
            "stages_count": 3,
            "avg_progress": 100.0
        }
    ],
    "sql_query": "SELECT p.name, p.status, COUNT(s.id) ...",
    "metadata": {
        "row_count": 2
    },
    "success": true
}
```

## Типы Запросов

### Statistics Queries (статистика)
- "Сколько проектов в системе?"
- "Количество активных объектов"
- "Средний прогресс по всем этапам"

### Distribution Queries (распределение)
- "Покажи проекты по статусам"
- "Распределение объектов по ответственным"
- "Статистика по отделам"

### Trend Queries (динамика)
- "Динамика создания проектов за 3 месяца"
- "Изменение прогресса проектов за неделю"
- "График завершенных задач по дням"

### Comparison Queries (сравнение)
- "Сравни прогресс проектов"
- "Топ-10 самых продуктивных сотрудников"
- "Какие проекты отстают от графика"

## Интеграция с Orchestrator

Analytics Agent также доступен через общий chat endpoint с автоматической маршрутизацией:

**Request:**
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Покажи статистику проектов по статусам",
    "user_id": "user-uuid",
    "thread_id": "analytics-session-1"
  }'
```

Orchestrator автоматически определит, что это аналитический запрос, и направит его в Analytics Agent.

## RBAC (Role-Based Access Control)

### Уровни доступа:

**admin (100):**
- Полный доступ ко всем данным
- Персональная информация
- Детальные отчеты

**manager (50):**
- Все проекты
- Агрегированные данные по сотрудникам
- Без email и телефонов

**engineer (30):**
- Только проекты, где пользователь участник
- Ограниченная информация о других сотрудниках

**viewer (10):**
- Только агрегированные данные
- Статистика без персональной информации
- Только COUNT, AVG, SUM

**guest (0):**
- Только общая статистика
- Максимум 5-10 записей
- Без имен и контактов

### Пример учета роли:

**Admin запрос:**
```sql
SELECT
    p.name,
    u.email,
    u.phone,
    COUNT(o.id) as objects
FROM projects p
JOIN profiles u ON u.id = p.created_by
GROUP BY p.id, u.email, u.phone
```

**Guest запрос (та же фраза):**
```sql
SELECT
    COUNT(*) as total_projects,
    AVG(progress) as avg_progress
FROM projects
LIMIT 10
```

## Error Handling

### Типы ошибок:

**SQL Error:**
```json
{
    "type": "text",
    "content": "Не удалось выполнить запрос. Попробуйте уточнить параметры.",
    "success": false,
    "error": "SQL syntax error"
}
```

**Permission Denied:**
```json
{
    "type": "text",
    "content": "У вас недостаточно прав для просмотра этих данных.",
    "success": false,
    "error": "Permission denied for role: guest"
}
```

**No Data Found:**
```json
{
    "type": "text",
    "content": "Данные не найдены. Попробуйте изменить фильтры или период.",
    "success": true,
    "metadata": {"row_count": 0}
}
```

## Frontend Integration Examples

### React с Chart.js

```jsx
import { useState } from 'react';
import { Chart as ChartJS, ArcElement, Tooltip, Legend } from 'chart.js';
import { Pie, Bar, Line } from 'react-chartjs-2';

ChartJS.register(ArcElement, Tooltip, Legend);

function AnalyticsDashboard() {
    const [result, setResult] = useState(null);

    const fetchAnalytics = async (query) => {
        const response = await fetch('/api/analytics', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query })
        });

        const data = await response.json();
        setResult(data);
    };

    const renderContent = () => {
        if (!result) return null;

        switch (result.type) {
            case 'chart':
                const ChartComponent = {
                    pie: Pie,
                    bar: Bar,
                    line: Line
                }[result.chart_config.type];

                return (
                    <ChartComponent
                        data={result.chart_config.data}
                        options={result.chart_config.options}
                    />
                );

            case 'table':
                return (
                    <table>
                        <thead>
                            <tr>
                                {Object.keys(result.content[0]).map(key => (
                                    <th key={key}>{key}</th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {result.content.map((row, i) => (
                                <tr key={i}>
                                    {Object.values(row).map((val, j) => (
                                        <td key={j}>{val}</td>
                                    ))}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                );

            case 'text':
                return <p style={{whiteSpace: 'pre-wrap'}}>{result.content}</p>;

            default:
                return <pre>{JSON.stringify(result, null, 2)}</pre>;
        }
    };

    return (
        <div>
            <input
                type="text"
                placeholder="Введите аналитический запрос..."
                onKeyPress={(e) => {
                    if (e.key === 'Enter') {
                        fetchAnalytics(e.target.value);
                    }
                }}
            />
            {renderContent()}
        </div>
    );
}
```

### Vue 3 с Chart.js

```vue
<template>
    <div class="analytics">
        <input
            v-model="query"
            @keyup.enter="fetchAnalytics"
            placeholder="Введите запрос..."
        />

        <div v-if="result">
            <Pie
                v-if="result.type === 'chart' && result.chart_config.type === 'pie'"
                :data="result.chart_config.data"
                :options="result.chart_config.options"
            />

            <table v-if="result.type === 'table'">
                <thead>
                    <tr>
                        <th v-for="key in Object.keys(result.content[0])">{{ key }}</th>
                    </tr>
                </thead>
                <tbody>
                    <tr v-for="row in result.content">
                        <td v-for="val in Object.values(row)">{{ val }}</td>
                    </tr>
                </tbody>
            </table>

            <p v-if="result.type === 'text'" style="white-space: pre-wrap">
                {{ result.content }}
            </p>
        </div>
    </div>
</template>

<script setup>
import { ref } from 'vue';
import { Pie } from 'vue-chartjs';

const query = ref('');
const result = ref(null);

const fetchAnalytics = async () => {
    const response = await fetch('/api/analytics', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query.value })
    });

    result.value = await response.json();
};
</script>
```

## Production Considerations

### 1. SQL Execution
В production замените mock данные на реальное выполнение SQL:

```python
# В analytics_agent.py, метод _execute_sql()
def _execute_sql(self, sql: str) -> List[Dict[str, Any]]:
    # Используйте Supabase RPC или psycopg2
    result = self.db.rpc('execute_analytics_query', {'query': sql}).execute()
    return result.data
```

Создайте Postgres функцию:
```sql
CREATE OR REPLACE FUNCTION execute_analytics_query(query TEXT)
RETURNS TABLE(result JSONB) AS $$
BEGIN
    -- Проверка безопасности
    IF query !~* '^SELECT' THEN
        RAISE EXCEPTION 'Only SELECT queries allowed';
    END IF;

    -- Выполнение запроса
    RETURN QUERY EXECUTE query;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
```

### 2. Caching
Добавьте кэширование для тяжелых запросов:

```python
from functools import lru_cache

@lru_cache(maxsize=100)
def _execute_sql_cached(self, sql: str) -> List[Dict[str, Any]]:
    return self._execute_sql(sql)
```

### 3. Rate Limiting
Ограничьте количество запросов:

```python
from fastapi import HTTPException
from slowapi import Limiter

limiter = Limiter(key_func=lambda: request.client.host)

@app.post("/api/analytics")
@limiter.limit("10/minute")
async def analytics_endpoint(...):
    ...
```

### 4. Async Execution
Для долгих запросов используйте фоновые задачи:

```python
from fastapi import BackgroundTasks

@app.post("/api/analytics/async")
async def analytics_async(request: AnalyticsRequest, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    background_tasks.add_task(process_analytics_async, task_id, request)
    return {"task_id": task_id, "status": "processing"}
```

## Testing

### Unit Tests

```python
# tests/test_analytics_agent.py
import pytest
from agents.analytics_agent import AnalyticsAgent

def test_parse_query():
    agent = AnalyticsAgent()
    result = agent._parse_user_query("Покажи проекты по статусам")

    assert result.intent == "chart"
    assert "projects" in result.entities
    assert result.chart_type == "pie"

def test_generate_sql():
    agent = AnalyticsAgent()
    parsed = AnalyticsQuery(
        intent="chart",
        entities=["projects"],
        metrics=["count"],
        chart_type="pie"
    )

    sql = agent._generate_sql(parsed)
    assert "SELECT" in sql.upper()
    assert "GROUP BY" in sql.upper()
```

### Integration Tests

```python
# tests/test_analytics_endpoint.py
from fastapi.testclient import TestClient
from server import app

client = TestClient(app)

def test_analytics_endpoint():
    response = client.post(
        "/api/analytics",
        json={"query": "Статистика проектов", "user_role": "admin"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] == True
    assert data["type"] in ["text", "table", "chart", "mixed"]
```

## Troubleshooting

### Проблема: "SQL execution failed"
**Решение:** Проверьте, что Postgres функция `execute_analytics_query` создана и имеет права SECURITY DEFINER.

### Проблема: "Permission denied"
**Решение:** Убедитесь, что роль пользователя корректно загружается из БД и передается в agent.

### Проблема: "Chart not rendering"
**Решение:** Проверьте, что на фронтенде установлен Chart.js и зарегистрированы нужные компоненты (ArcElement, BarElement и т.д.).

### Проблема: "Slow queries"
**Решение:**
1. Добавьте индексы на часто используемые колонки (status, created_at, project_id)
2. Используйте LIMIT для больших выборок
3. Включите кэширование

## Next Steps

1. **Расширение SQL генератора** - добавить поддержку сложных JOIN, подзапросов
2. **Больше типов графиков** - scatter, radar, mixed charts
3. **Экспорт данных** - CSV, Excel, PDF export
4. **Scheduled Reports** - автоматическая генерация отчетов по расписанию
5. **ML Insights** - предсказание трендов, аномалии, рекомендации

---

**Разработано для Eneca AI Bot** | Analytics Agent v1.0
