# Следующие шаги для Eneca AI Bot

## Что уже реализовано ✅

### 1. Архитектура агентов
- ✅ **BaseAgent** - базовый класс для всех агентов
- ✅ **OrchestratorAgent** - главный оркестратор с routing логикой
- ✅ **RAGAgent** - агент для поиска в базе знаний

### 2. Система маршрутизации
- ✅ Оркестратор анализирует запрос и решает, нужен ли инструмент
- ✅ Простые вопросы обрабатываются без делегирования
- ✅ Специфические вопросы о приложении передаются RAG-агенту
- ✅ Интеграция через LangChain Tools и AgentExecutor

### 3. Инфраструктура
- ✅ Конфигурация для Supabase (URL, KEY)
- ✅ Модуль для работы с Supabase Vector Store
- ✅ OpenAI Embeddings для векторного поиска
- ✅ Система промптов для оркестратора и RAG-агента
- ✅ Тесты для проверки маршрутизации

---

## Что нужно сделать дальше 🚀

### 1. Настроить Supabase для RAG
**Приоритет:** Высокий

#### Шаг 1: Добавить креденшиалы Supabase
Обновите файл `.env`:
```env
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_KEY=your-supabase-anon-key
```

#### Шаг 2: Создать таблицу для документов в Supabase
Выполните SQL в Supabase Dashboard:

```sql
-- Включить расширение pgvector
create extension if not exists vector;

-- Создать таблицу для документов
create table documents (
  id bigserial primary key,
  content text not null,
  metadata jsonb,
  embedding vector(1536)  -- Размерность для OpenAI text-embedding-3-small
);

-- Создать функцию для поиска похожих документов
create or replace function match_documents (
  query_embedding vector(1536),
  match_threshold float,
  match_count int
)
returns table (
  id bigint,
  content text,
  metadata jsonb,
  similarity float
)
language sql stable
as $$
  select
    documents.id,
    documents.content,
    documents.metadata,
    1 - (documents.embedding <=> query_embedding) as similarity
  from documents
  where 1 - (documents.embedding <=> query_embedding) > match_threshold
  order by similarity desc
  limit match_count;
$$;

-- Создать индекс для быстрого поиска
create index on documents using ivfflat (embedding vector_cosine_ops)
with (lists = 100);
```

#### Шаг 3: Загрузить документы в базу знаний
Создайте скрипт для загрузки ваших документов:

```python
from core.vector_store import vector_store_manager

# Пример загрузки документов
documents = [
    "Чтобы создать новый проект в Eneca, откройте раздел 'Проекты' и нажмите 'Новый проект'.",
    "Раздел настроек находится в правом верхнем углу, нажмите на иконку профиля и выберите 'Настройки'.",
    # ... добавьте свои документы
]

metadatas = [
    {"source": "manual", "category": "projects"},
    {"source": "manual", "category": "settings"},
    # ... метаданные для каждого документа
]

# Загрузить в Supabase
vector_store_manager.add_documents(documents, metadatas)
print("Документы успешно загружены!")
```

### 2. Добавить память разговоров (Conversation Memory)
**Приоритет:** Средний

Сейчас бот не запоминает историю диалога. Добавьте память:

```python
# В agents/orchestrator.py
from langchain.memory import ConversationBufferMemory

class OrchestratorAgent(BaseAgent):
    def __init__(self, ...):
        # ... существующий код ...

        # Добавить память
        self.memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True
        )
```

### 3. Интеграция с Telegram
**Приоритет:** Высокий

Создайте Telegram бота:

```python
# bot/telegram_bot.py
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from agents.orchestrator import OrchestratorAgent
from core.config import settings

async def start(update: Update, context):
    await update.message.reply_text("Привет! Я Eneca AI Bot. Чем могу помочь?")

async def handle_message(update: Update, context):
    agent = OrchestratorAgent()
    user_message = update.message.text
    response = agent.process_message(user_message)
    await update.message.reply_text(response)

def main():
    app = Application.builder().token(settings.bot_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
```

### 4. Добавить дополнительных агентов
**Приоритет:** Низкий

Создайте агентов из вашего n8n workflow:

- **Plan_by_day** - агент для планирования дня
- **Notification** - агент для рассылок
- **Summary_tool** - агент для отчётов

Каждый агент создаётся как отдельный файл в `agents/` и добавляется как Tool в оркестратор.

### 5. Добавить персонализацию
**Приоритет:** Средний

Добавьте контекст пользователя в промпт оркестратора:

```python
# В orchestrator.py
def _build_user_context(self, user_id: str) -> str:
    # Получить данные пользователя из БД
    user = get_user_from_db(user_id)
    return f"""
    User ID: {user.id}
    Name: {user.name}
    Email: {user.email}
    Role: {user.role}
    """
```

---

## Тестирование

### Тестирование без Supabase (текущее состояние)
```bash
python test_bot.py
```

Ожидаемое поведение:
- Простые вопросы - бот отвечает сам
- Вопросы о приложении - бот пытается использовать RAG, но сообщает, что база знаний недоступна

### Тестирование с Supabase (после настройки)
После добавления креденшиалов и загрузки документов бот будет отвечать на специфические вопросы о приложении на основе данных из векторной БД.

---

## Структура проекта

```
Eneca_AI_bot/
├── agents/
│   ├── __init__.py
│   ├── base.py                 # Базовый класс агента
│   ├── orchestrator.py         # Главный оркестратор
│   └── rag_agent.py           # RAG агент для поиска в БЗ
├── core/
│   ├── __init__.py
│   ├── config.py              # Конфигурация (Settings)
│   └── vector_store.py        # Supabase Vector Store
├── prompts/
│   ├── orchestrator.md        # Промпт оркестратора
│   └── rag_agent.md          # Промпт RAG агента
├── .env                       # Секреты и настройки
├── .env.example              # Пример конфигурации
├── app.py                    # CLI интерфейс
├── test_bot.py              # Тесты
└── requirements.txt         # Зависимости
```

---

## Полезные команды

```bash
# Запуск тестов
python test_bot.py

# Запуск CLI бота
python app.py

# Проверка установленных пакетов
pip list | grep langchain

# Обновление зависимостей
pip install -r requirements.txt --upgrade
```

---

## Контакты и поддержка

Если возникли вопросы:
1. Проверьте логи в папке `logs/`
2. Убедитесь, что все переменные окружения в `.env` заполнены
3. Проверьте, что Supabase таблица создана правильно
