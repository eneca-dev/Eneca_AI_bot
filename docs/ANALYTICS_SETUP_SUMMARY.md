# Analytics Agent - Setup Summary

## ✅ Что реализовано

### 1. AnalyticsAgent Class ([agents/analytics_agent.py](../agents/analytics_agent.py))
Полнофункциональный агент для аналитики данных с возможностями:
- **Natural Language Parsing** - парсинг запросов на естественном языке в структурированный формат
- **SQL Generation** - автоматическая генерация безопасных SELECT-запросов
- **Data Analysis** - статистический анализ, агрегация, сравнения
- **Chart Preparation** - готовые конфигурации для Chart.js (pie, bar, line)
- **RBAC Integration** - учет ролей пользователей при генерации SQL

### 2. FastAPI Endpoint ([server.py](../server.py))
Добавлен новый endpoint `/api/analytics`:
- **Request Model:** `AnalyticsRequest` (query, user_id, user_role, metadata)
- **Response Model:** `AnalyticsResponse` (type, content, sql_query, chart_config, metadata)
- **Authentication:** Интеграция с существующей системой API ключей
- **RBAC:** Автоматическая загрузка роли пользователя из Supabase

### 3. Configuration
Analytics Agent НЕ регистрируется в `config/agents.yaml`:
- **Standalone Service** - работает независимо от Orchestrator
- **Direct Endpoint** - `/api/analytics` в server.py
- **Model:** gpt-4o (настраивается в agents/analytics_agent.py)
- **Temperature:** 0.2 (точность для SQL)
- **NOTE:** Специально исключен из agents.yaml для независимости

### 4. System Prompt ([prompts/analytics_agent.md](../prompts/analytics_agent.md))
Детальный промпт с:
- Схемой базы данных (projects, stages, objects, sections, profiles)
- Примерами SQL-запросов
- Правилами безопасности и RBAC
- Форматами ответов

### 5. Documentation ([docs/ANALYTICS_AGENT.md](../docs/ANALYTICS_AGENT.md))
Полная документация с:
- Примерами API запросов
- Frontend интеграцией (React, Vue)
- Production considerations
- Testing примерами

## 📋 Архитектура

Analytics Agent — **полностью независимый сервис**, работающий параллельно с Orchestrator.

**ВАЖНО:** Analytics Agent НЕ является частью Orchestrator и НЕ зарегистрирован в `config/agents.yaml`.

```
┌─────────────────────────────────────────────────────────────────┐
│                      Frontend / Client                          │
│                      (AI Dashboard)                             │
└──────────────────┬────────────────────────┬─────────────────────┘
                   │                        │
                   │ Separate Paths         │
                   │ (NO shared routing)    │
                   ↓                        ↓
    ┌──────────────────────────┐  ┌──────────────────────────┐
    │  POST /api/chat          │  │  POST /api/analytics     │
    │  (Chat/Conversation)     │  │  (Data Analysis Only)    │
    │                          │  │                          │
    │  Routes to Orchestrator  │  │  Direct to Analytics     │
    └──────────┬───────────────┘  └──────────┬───────────────┘
               │                              │
               ↓                              ↓
    ┌──────────────────────┐      ┌──────────────────────────┐
    │  OrchestratorAgent   │      │  AnalyticsAgent          │
    │  (LangGraph ReAct)   │      │  (Standalone Service)    │
    │                      │      │                          │
    │  Tools:              │      │  Capabilities:           │
    │  - MCPAgent          │      │  - SQL Generation        │
    │  - RAGAgent          │      │  - Data Analysis         │
    │  (NOT Analytics!)    │      │  - Chart Preparation     │
    └──────────┬───────────┘      └──────────┬───────────────┘
               │                              │
               ↓                              ↓
    ┌──────────────────────┐      ┌──────────────────────────┐
    │  Supabase DB         │      │  Supabase DB             │
    │  (RAG vectors)       │      │  (Analytics queries)     │
    │  MCP Server          │      │  (Direct SQL/RPC)        │
    └──────────────────────┘      └──────────────────────────┘
```

**Key Differences:**
- **Chat flow:** User → Orchestrator → MCPAgent/RAGAgent
- **Analytics flow:** User → Analytics Endpoint (bypasses Orchestrator)
- **No overlap:** Analytics does NOT appear as a tool in Orchestrator

## 🚀 Использование

### Endpoint URL
```
POST http://localhost:8000/api/analytics
```

### Пример запроса
```bash
curl -X POST http://localhost:8000/api/analytics \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{
    "query": "Покажи количество проектов по статусам",
    "user_id": "user-uuid",
    "user_role": "manager"
  }'
```

### Пример ответа
```json
{
    "type": "chart",
    "content": [
        {"label": "active", "value": 15},
        {"label": "completed", "value": 8}
    ],
    "chart_config": {
        "type": "pie",
        "data": {...},
        "options": {...}
    },
    "sql_query": "SELECT status, COUNT(*) ...",
    "metadata": {"row_count": 2},
    "success": true
}
```

## ⚙️ Конфигурация

### Environment Variables
Все необходимые переменные уже настроены в `.env`:
- `OPENAI_API_KEY` - для LLM
- `SUPABASE_CHAT_URL` и `SUPABASE_CHAT_SERVICE_KEY` - для доступа к БД
- `API_KEY` (опционально) - для защиты endpoint

### Dependencies
Все библиотеки уже есть в `requirements.txt`:
- `langchain`, `langchain-openai` - LLM
- `pydantic` - validation
- `fastapi`, `uvicorn` - API server
- `supabase` - database client

## 🔧 Что нужно доработать для Production

### 1. Real SQL Execution
Сейчас используются mock данные. Нужно:

**Вариант A: Supabase RPC**
```python
# В analytics_agent.py
def _execute_sql(self, sql: str) -> List[Dict[str, Any]]:
    result = self.db.rpc('execute_analytics_query', {'query': sql}).execute()
    return result.data
```

Создать Postgres функцию:
```sql
CREATE OR REPLACE FUNCTION execute_analytics_query(query TEXT)
RETURNS TABLE(result JSONB) AS $$
BEGIN
    IF query !~* '^SELECT' THEN
        RAISE EXCEPTION 'Only SELECT queries allowed';
    END IF;
    RETURN QUERY EXECUTE format('SELECT row_to_json(t) FROM (%s) t', query);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
```

**Вариант B: psycopg2 Direct Connection**
```python
import psycopg2
from psycopg2.extras import RealDictCursor

def _execute_sql(self, sql: str) -> List[Dict[str, Any]]:
    conn = psycopg2.connect(settings.postgres_connection_string)
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(sql)
        return cursor.fetchall()
```

### 2. Enhanced SQL Generation
Текущая реализация использует базовые шаблоны. Можно улучшить:
- Использовать LangChain SQL Toolkit
- Добавить SQL query validation
- Кэшировать часто используемые запросы

### 3. Database Schema Introspection
Добавить автоматическое чтение схемы БД:
```python
def _load_schema_info(self):
    """Load table schemas from database"""
    schema = self.db.rpc('get_table_schemas').execute()
    return schema.data
```

### 4. Performance Optimizations
- Добавить индексы на часто используемые колонки
- Использовать connection pooling
- Кэшировать результаты запросов (Redis)
- Async SQL execution для долгих запросов

### 5. Advanced Analytics
- Trend analysis (линейная регрессия, прогнозы)
- Anomaly detection (выбросы в данных)
- ML-based insights (clustering, classification)

## 🧪 Testing

### Локальное тестирование
```bash
# Запуск сервера
python server.py

# Тест endpoint (в другом терминале)
curl -X POST http://localhost:8000/api/analytics \
  -H "Content-Type: application/json" \
  -d '{"query": "Статистика проектов", "user_role": "admin"}'
```

### Unit Tests
```bash
pytest tests/test_analytics_agent.py -v
```

### Integration Tests
```bash
pytest tests/test_analytics_endpoint.py -v
```

## 📦 Deployment

Analytics Agent деплоится вместе с основным сервером:

```bash
# Docker
docker-compose up -d

# Проверка
curl http://localhost:8000/health
# Должен показать analytics_agent в списке агентов
```

## 🔗 Integration с Frontend

### React Example
```jsx
const response = await fetch('/api/analytics', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        query: 'Покажи статистику проектов',
        user_id: currentUser.id
    })
});

const data = await response.json();

if (data.type === 'chart') {
    <Pie data={data.chart_config.data} options={data.chart_config.options} />
}
```

### Vue Example
```vue
<script setup>
const fetchAnalytics = async (query) => {
    const res = await fetch('/api/analytics', {
        method: 'POST',
        body: JSON.stringify({ query })
    });
    return res.json();
};
</script>
```

## 📊 Типичные Use Cases

### 1. Dashboard Overview
```
Query: "Покажи общую статистику по всем проектам"
Output: Text report с ключевыми метриками
```

### 2. Status Distribution
```
Query: "Распределение проектов по статусам"
Output: Pie chart с процентами
```

### 3. Progress Tracking
```
Query: "График прогресса активных проектов"
Output: Bar chart с сортировкой
```

### 4. Team Performance
```
Query: "Топ-10 самых продуктивных сотрудников"
Output: Table с сортировкой
```

### 5. Trend Analysis
```
Query: "Динамика создания проектов за последние 3 месяца"
Output: Line chart с временной шкалой
```

## 📝 Next Steps

1. ✅ **DONE:** Базовая структура и endpoint
2. ⏳ **TODO:** Реальное SQL execution (RPC или psycopg2)
3. ⏳ **TODO:** Unit и integration tests
4. ⏳ **TODO:** Frontend интеграция (React/Vue компоненты)
5. ⏳ **TODO:** Enhanced SQL generation с LangChain SQL Toolkit
6. ⏳ **TODO:** Caching и performance optimization
7. ⏳ **TODO:** ML-based insights (опционально)

## 🆘 Support

Для вопросов и troubleshooting смотрите:
- [Full Documentation](./ANALYTICS_AGENT.md)
- [Analytics Agent Code](../agents/analytics_agent.py)
- [System Prompt](../prompts/analytics_agent.md)

---

**Status:** ✅ Ready for testing with mock data | ⏳ Needs production SQL implementation
