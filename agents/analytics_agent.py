"""Analytics Agent for data analysis, reporting, and visualization"""
from pathlib import Path
from typing import Dict, Any, List, Optional
import json
import time
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from agents.base import BaseAgent
from database.supabase_client import supabase_db_client
from core.config import settings
from agents.sql_generator import SQLGenerator

# Import shared models to avoid circular import
from agents.analytics_models import FilterOptions, AnalyticsQuery, AnalyticsResult


class AnalyticsAgent(BaseAgent):
    """
    Analytics Agent for data analysis and reporting

    Capabilities:
    - SQL query generation and execution
    - Statistical analysis
    - Report generation
    - Chart data preparation (for frontend rendering)
    - Comparison and trend analysis
    """

    def __init__(self, model: str = None, temperature: float = None):
        """
        Initialize Analytics agent

        Args:
            model: OpenAI model name (defaults to config value)
            temperature: Lower for precise SQL, higher for creative insights
        """
        model = model or settings.orchestrator_model
        temperature = temperature if temperature is not None else 0.2  # Precise for SQL

        super().__init__(model=model, temperature=temperature)
        self.db = supabase_db_client

        # Configure LLM with structured output
        self.query_llm = self.llm.with_structured_output(AnalyticsQuery)

        # Initialize SQL Generator
        self.sql_generator = SQLGenerator()

        # Initialize circuit breaker for SQL execution protection
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60
        )

        logger.info(f"AnalyticsAgent initialized with model {model}")

    def _get_default_prompt(self) -> str:
        """Load system prompt from prompts/analytics_agent.md"""
        prompt_path = Path(__file__).parent.parent / "prompts" / "analytics_agent.md"

        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                prompt = f.read()
            logger.debug(f"Loaded Analytics agent prompt from {prompt_path}")
            return prompt
        except FileNotFoundError:
            logger.warning(f"Prompt file not found at {prompt_path}, using default")
            return self._get_fallback_prompt()

    def _get_fallback_prompt(self) -> str:
        """Fallback prompt if file not found"""
        return """Ты — Analytics Agent для системы управления проектами Eneca.

Твоя задача: анализировать данные, генерировать отчеты и создавать аналитику по запросу пользователя.

Доступные таблицы в базе данных:
- projects: проекты (id, name, status, created_at, updated_at)
- stages: этапы проектов (id, project_id, name, start_date, end_date, progress)
- objects: объекты в этапах (id, stage_id, name, responsible_id, status)
- sections: разделы в объектах (id, object_id, name, progress)
- profiles: пользователи (id, email, first_name, last_name, job_title, department)

Возможности:
1. Генерация SQL запросов для аналитики
2. Статистический анализ данных
3. Подготовка данных для графиков
4. Сравнительный анализ
5. Генерация отчетов

ВАЖНО:
- Все SQL запросы должны быть безопасными (только SELECT)
- Всегда используй параметризованные запросы
- Возвращай структурированные данные для фронтенда
- Учитывай права доступа пользователя (role-based)
"""

    def _parse_user_query(self, query: str, user_role: Optional[str] = None) -> AnalyticsQuery:
        """
        Parse natural language query into structured analytics query

        Args:
            query: User's natural language query
            user_role: User's role for access control

        Returns:
            Structured AnalyticsQuery
        """
        prompt = f"""Проанализируй запрос пользователя и преобразуй его в структурированный формат.

Запрос пользователя: {query}
Роль пользователя: {user_role or 'guest'}

Определи:
1. intent: тип операции (report, chart, statistics, sql_query, comparison, complex_join, ranking)
   - chart: для РАСПРЕДЕЛЕНИЯ, ГРУППИРОВКИ, ДИАГРАММ (например: "распределение проектов по статусам", "сколько проектов в каждом статусе")
   - statistics: для СТАТИСТИКИ, ПОДСЧЕТА (например: "статистика по проектам", "сколько всего задач")
   - ranking: ТОП N запросы с группировкой и подсчетом (например: "топ 3 менеджера по проектам", "какие 5 сотрудников ведут больше всего задач")
   - complex_join: если запрос требует данные из НЕСКОЛЬКИХ таблиц (например: "объекты с менеджерами и бюджетом", "проекты с сотрудниками")
   - report: если запрос для ОДНОЙ таблицы (например: "список проектов", "мои этапы")

   ВАЖНО: Если запрос содержит "распределение", "по статусам", "сколько в каждом", "диаграмма", "график" → используй intent="chart"!
2. entities: какие сущности затрагивает запрос (projects, stages, objects, sections, tasks, profiles, view_employee_workloads, v_budgets_full, view_project_dashboard)
   - Для complex_join: укажи ВСЕ нужные таблицы в порядке приоритета (главная таблица первой)
3. requested_columns: КАКИЕ ИМЕННО колонки запросил пользователь (логические имена)
   - "покажи проекты" → ["name"] (только названия)
   - "проекты с менеджерами" → ["name", "first_name", "last_name"]
   - "вся информация по проектам" → ["name", "status", "description", "created_at", "updated_at"]
   - "активные проекты" → ["name", "status"]
   - "проекты с бюджетом" → ["name", "total_amount", "spent"]
   - "проекты по датам" или "с датами" → ["name", "created_at"] (ОБЯЗАТЕЛЬНО включай created_at!)
   - "активные проекты по датам" → ["name", "status", "created_at"]
   - [] = автоматический выбор минимальных колонок

   ВАЖНО: Если в запросе есть слова "по датам", "с датами", "даты", "когда созданы" - ОБЯЗАТЕЛЬНО добавляй "created_at" в requested_columns!
4. metrics: какие метрики нужны (count, sum, avg, progress, status_distribution, loading_rate, budget, spent, hours)
5. filters: какие фильтры применить:
   - status: статус (active, completed, in_progress)
   - min_budget/max_budget: для условий "больше 1000", "меньше 5000", "от 1000 до 5000"
   - min_hours/max_hours: для часов работы
   - min_progress/max_progress: для процента готовности
   - date_range: временной диапазон
6. aggregation: группировка (daily, weekly, monthly, by_user, by_project)
7. chart_type: тип визуализации:
   - line: линейный график (тренды во времени, динамика)
   - bar: столбчатая диаграмма (сравнение категорий)
   - area: график с областями (объёмные данные, накопление)
   - pie: круговая диаграмма (доли от целого, распределение)
   - radar: лепестковая диаграмма (многомерное сравнение показателей)
   - radialBar: радиальная диаграмма (прогресс, рейтинги, процент выполнения)
   - table: таблица (детальные данные)
8. personalized: персонализированный запрос (true если есть слова "мой/моя/мои/мне", иначе false)
9. require_all_entities: если запрос ТРЕБУЕТ наличия данных из связанных таблиц (true = INNER JOIN, false = LEFT JOIN)
   - true: когда говорят "С чем-то" ("объекты С именами ответственных", "проекты С бюджетом", "задачи С сотрудниками")
   - true: когда есть фильтры на связанную таблицу ("бюджет > 1000" означает что бюджет ДОЛЖЕН быть)
   - false: когда говорят "и их что-то" ("проекты и их бюджеты" - вернуть все проекты, даже без бюджета)
10. limit: для ТОП N запросов - число N (например: "топ 3" → limit=3, "топ 5" → limit=5, "первые 10" → limit=10)
11. order_by: по какой метрике сортировать (count, total_amount, spent, hours)
12. order_direction: направление сортировки (desc для "больше всего", asc для "меньше всего")
13. group_by_entity: для ranking - по какой сущности группировать (profiles для "менеджеры/сотрудники", projects для "проекты")
14. exclude_related: если запрос ищет сущности БЕЗ связанных данных (true = LEFT JOIN + WHERE NULL, false = обычное поведение)
   - true: когда говорят "БЕЗ чего-то", "НЕТ чего-то", "У КОТОРЫХ НЕТ" ("сотрудники без задач", "проекты без бюджета", "объекты у которых нет ответственных")
   - false: все остальные случаи

КРИТИЧНЫЕ ПРАВИЛА ДЛЯ ВЫБОРА ENTITY (читай ВНИМАТЕЛЬНО слова в запросе):
- Проект/проекты/проектов → projects
- Этап/этапы/этапов/стадия/стадии → stages
- Объект/объекты/объектов → objects
- Раздел/разделы/разделов/секция → sections
- Задача/задачи/задач/таск → tasks
- Сотрудник/сотрудники/пользователь/юзер/человек → profiles
- Загрузка/занятость/перегружен/кто загружен → view_employee_workloads
- Бюджет/финансы/деньги/потрачено/остаток/расход → v_budgets_full
- Часы/план часов/факт часов/трудозатраты → view_project_dashboard

ВАЖНО: Если в запросе явно написано "этапы" или "стадии" - НЕ ВЫБИРАЙ projects! Выбирай stages!
ВАЖНО: Если в запросе явно написано "объекты" - НЕ ВЫБИРАЙ projects! Выбирай objects!
ВАЖНО: Если в запросе явно написано "разделы" - НЕ ВЫБИРАЙ projects! Выбирай sections!

КРИТИЧНО: Для entities используй ТОЛЬКО то, что ЯВНО указано в запросе!
- "Активные проекты с менеджерами" → entities=["projects", "profiles"] (НЕ добавляй v_budgets_full!)
- "Проекты с бюджетом" → entities=["projects", "v_budgets_full"] (НЕ добавляй profiles!)
- "Активные проекты" → entities=["projects"], filters={{"status": "active"}} (НЕ добавляй profiles или budgets!)
- "Проекты" → entities=["projects"] (ТОЛЬКО проекты, без дополнительных таблиц!)

Примеры с requested_columns:
- "Покажи проекты" → entities=["projects"], requested_columns=["name"]
- "Активные проекты" → entities=["projects"], requested_columns=["name", "status"], filters={{"status": "active"}}
- "Вся информация по проектам" → entities=["projects"], requested_columns=["name", "status", "description", "created_at", "updated_at"]
- "Мои проекты" → entities=["projects"], requested_columns=["name"], personalized=true
- "Покажи этапы" → entities=["stages"], requested_columns=["name"]
- "Статус всех этапов" → entities=["stages"], requested_columns=["name", "status"]
- "Список объектов" → entities=["objects"], requested_columns=["name"]
- "Мои объекты" → entities=["objects"], requested_columns=["name"], personalized=true
- "Разделы проекта" → entities=["sections"]
- "Задачи сотрудников" → entities=["tasks"]
- "Кто перегружен?" → entities=["view_employee_workloads"]
- "Бюджет проектов" → entities=["v_budgets_full"], filters={{"entity_type": "project"}}
- "Топ 5 проектов по бюджету" → entities=["v_budgets_full"], chart_type="bar"
- "Сколько потрачено денег" → entities=["v_budgets_full"], metrics=["spent"]
- "Остаток бюджета" → entities=["v_budgets_full"], metrics=["remaining"]
- "Часы по проектам" → entities=["view_project_dashboard"]

ПРИМЕРЫ CHART/STATISTICS (распределение, статистика, группировка):
- "Распределение проектов по статусам" → intent="chart", entities=["projects"], chart_type="pie", metrics=["status_distribution"]
- "Сколько проектов в каждом статусе" → intent="chart", entities=["projects"], chart_type="bar"
- "Статистика по проектам" → intent="statistics", entities=["projects"], metrics=["count"]
- "Распределение задач по статусам" → intent="chart", entities=["tasks"], chart_type="pie"
- "Сколько объектов у каждого ответственного" → intent="chart", entities=["objects"], chart_type="bar"
- "График загрузки сотрудников" → intent="chart", entities=["view_employee_workloads"], chart_type="bar"
- "Динамика создания проектов по месяцам" → intent="chart", entities=["projects"], chart_type="line", aggregation="monthly"
- "Накопительный график бюджета" → intent="chart", entities=["v_budgets_full"], chart_type="area"
- "Сравнение показателей проекта" → intent="chart", entities=["projects"], chart_type="radar"
- "Прогресс выполнения проектов" → intent="chart", entities=["projects"], chart_type="radialBar", metrics=["progress"]
- "Рейтинг сотрудников по загрузке" → intent="chart", entities=["view_employee_workloads"], chart_type="radialBar"

ПРИМЕРЫ ОДНОЙ ТАБЛИЦЫ (intent=report):
- "Активные проекты" → intent="report", entities=["projects"], requested_columns=["name", "status"], filters={{"status": "active"}}
- "Активные проекты по датам" → intent="report", entities=["projects"], requested_columns=["name", "status", "created_at"], filters={{"status": "active"}}
- "Проекты с датами" → intent="report", entities=["projects"], requested_columns=["name", "created_at"]
- "Все проекты" → intent="report", entities=["projects"], requested_columns=["name"]
- "Список этапов" → intent="report", entities=["stages"], requested_columns=["name"]
- "Мои объекты" → intent="report", entities=["objects"], requested_columns=["name"], personalized=true

ПРИМЕРЫ С ФИЛЬТРАМИ НА СВЯЗАННЫЕ ТАБЛИЦЫ:
- "Активные проекты с бюджетом больше 1000" → intent="complex_join", entities=["projects", "v_budgets_full"], filters={{"status": "active", "min_budget": 1000}}, require_all_entities=true
- "Проекты с бюджетом от 1000 до 5000" → intent="complex_join", entities=["projects", "v_budgets_full"], filters={{"min_budget": 1000, "max_budget": 5000}}, require_all_entities=true
- "Объекты с ответственными где прогресс больше 50%" → intent="complex_join", entities=["objects", "profiles"], filters={{"min_progress": 50}}, require_all_entities=true
- "Проекты без бюджета" → intent="complex_join", entities=["projects", "v_budgets_full"], exclude_related=true
- "Сотрудники без задач" → intent="complex_join", entities=["profiles", "tasks"], exclude_related=true
- "Сотрудники у которых нет активных задач на этой неделе" → intent="complex_join", entities=["profiles", "tasks"], filters={{"status": "active", "date_range": "this_week"}}, exclude_related=true
- "Объекты без ответственных" → intent="complex_join", entities=["objects", "profiles"], exclude_related=true

ПРИМЕРЫ COMPLEX_JOIN (ТОЛЬКО если явно указаны несколько сущностей):
- "Объекты С именами ответственных" → intent="complex_join", entities=["objects", "profiles"], requested_columns=["name", "first_name", "last_name"], require_all_entities=true
- "Активные проекты С менеджерами" → intent="complex_join", entities=["projects", "profiles"], requested_columns=["name", "status", "first_name", "last_name"], filters={{"status": "active"}}, require_all_entities=true
- "Проекты С бюджетом" → intent="complex_join", entities=["projects", "v_budgets_full"], requested_columns=["name", "total_amount", "spent"], require_all_entities=true
- "Вся информация по проектам с менеджерами" → intent="complex_join", entities=["projects", "profiles"], requested_columns=["name", "status", "description", "created_at", "first_name", "last_name", "email"], require_all_entities=true
- "Проекты и их бюджеты" → intent="complex_join", entities=["projects", "v_budgets_full"], requested_columns=["name", "total_amount"], require_all_entities=false
- "Проекты и их менеджеры" → intent="complex_join", entities=["projects", "profiles"], requested_columns=["name", "first_name", "last_name"], require_all_entities=false

ПРИМЕРЫ RANKING (ТОП N с группировкой):
- "Какие 3 менеджера ведут больше всего активных проектов?" → intent="ranking", entities=["projects"], group_by_entity="profiles", filters={{"status": "active"}}, limit=3, order_by="count", order_direction="desc"
- "Топ 5 сотрудников по количеству задач" → intent="ranking", entities=["tasks"], group_by_entity="profiles", limit=5, order_by="count", order_direction="desc"
- "Кто меньше всего загружен?" → intent="ranking", entities=["tasks"], group_by_entity="profiles", limit=5, order_by="count", order_direction="asc"
- "Топ 10 проектов по бюджету" → intent="ranking", entities=["projects", "v_budgets_full"], group_by_entity="projects", limit=10, order_by="total_amount", order_direction="desc"
- "Первые 3 этапа по прогрессу" → intent="ranking", entities=["stages"], group_by_entity="stages", limit=3, order_by="progress", order_direction="desc"

НЕПРАВИЛЬНЫЕ примеры (НЕ делай так):
- "Активные проекты с менеджерами" → ❌ entities=["projects", "profiles", "v_budgets_full"] (НЕ добавляй бюджет!)
- "Проекты" → ❌ entities=["projects", "profiles"] (НЕ добавляй profiles если не упомянуты!)
"""

        try:
            parsed = self.query_llm.invoke(prompt)
            logger.info(f"Parsed query: {parsed}")
            return parsed
        except Exception as e:
            logger.error(f"Error parsing query: {e}")
            # Fallback: try to guess entity from query text
            query_lower = query.lower()
            entity = "projects"  # default

            # Check for keywords in order of specificity
            if any(word in query_lower for word in ['загрузк', 'занятост', 'перегруж']):
                entity = "view_employee_workloads"
            elif any(word in query_lower for word in ['бюджет', 'финанс', 'деньги', 'потрач', 'остаток', 'расход']):
                entity = "v_budgets_full"
            elif any(word in query_lower for word in ['час', 'трудозатрат']):
                entity = "view_project_dashboard"
            elif any(word in query_lower for word in ['этап', 'стади']):
                entity = "stages"
            elif any(word in query_lower for word in ['объект']):
                entity = "objects"
            elif any(word in query_lower for word in ['раздел', 'секци']):
                entity = "sections"
            elif any(word in query_lower for word in ['задач', 'таск']):
                entity = "tasks"
            elif any(word in query_lower for word in ['сотрудник', 'пользовател', 'юзер', 'человек']):
                entity = "profiles"
            elif any(word in query_lower for word in ['проект']):
                entity = "projects"

            logger.warning(f"Fallback entity selection: {entity}")

            return AnalyticsQuery(
                intent="report",
                entities=[entity],
                metrics=["count"]
            )

    def _generate_sql(
        self,
        parsed_query: AnalyticsQuery,
        user_role: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> str:
        """
        Generate SQL using SQLGenerator with RBAC

        Args:
            parsed_query: Structured analytics query
            user_role: User's role for RBAC filtering
            user_id: User's ID for personalized queries

        Returns:
            SQL query string
        """
        # Generate SQL with parameters
        sql, params = self.sql_generator.generate_sql(
            parsed_query,
            user_role or 'guest',
            user_id
        )

        # Inject parameters safely (escape SQL injection)
        sql = self.sql_generator._inject_parameters_safe(sql, params)

        logger.info(f"Generated SQL: {sql[:200]}...")
        return sql

    def _execute_sql(
        self,
        sql: str,
        user_role: str = 'guest'
    ) -> List[Dict[str, Any]]:
        """
        Execute SQL with retry logic and circuit breaker

        Args:
            sql: SQL query (SELECT only)
            user_role: User role for sensitive column filtering

        Returns:
            Query results as list of dicts
        """
        # Security check
        if not sql.strip().upper().startswith("SELECT"):
            raise ValueError("Only SELECT queries are allowed")

        logger.info(f"Executing SQL for role={user_role}")

        try:
            # Execute with retry
            data = self._execute_sql_with_retry(sql, user_role)

            # Filter sensitive columns based on role
            data = self._filter_sensitive_columns(data, user_role)

            return data

        except Exception as e:
            logger.error(f"SQL execution failed after retries: {e}")
            return []

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10)
    )
    def _execute_sql_with_retry(
        self,
        sql: str,
        user_role: str
    ) -> List[Dict[str, Any]]:
        """
        Execute SQL with retry and circuit breaker

        Args:
            sql: SQL query string
            user_role: User role for logging

        Returns:
            Query results

        Raises:
            Exception: If circuit breaker is open or execution fails
        """
        # Check circuit breaker
        if self.circuit_breaker.is_open():
            logger.warning("Circuit breaker OPEN - skipping SQL execution")
            raise Exception("Circuit breaker open")

        # Check if Supabase client is available
        if not self.db.is_available():
            logger.error("Supabase client not available")
            raise Exception("Supabase client not initialized")

        try:
            # Call RPC function
            response = self.db.client.rpc(
                'execute_analytics_query',
                {'query_text': sql, 'user_role_name': user_role}
            ).execute()

            # Record success
            self.circuit_breaker.record_success()

            # Parse JSONB result
            return self._parse_jsonb_result(response.data)

        except Exception as e:
            # Record failure
            self.circuit_breaker.record_failure()
            logger.error(f"RPC execution failed: {e}")
            raise

    def _parse_jsonb_result(self, data: List[Dict]) -> List[Dict]:
        """
        Parse JSONB from RPC response

        Args:
            data: Raw RPC response data

        Returns:
            Parsed list of dicts
        """
        if not data:
            return []

        # RPC returns [{"result": {...}}, {"result": {...}}, ...]
        if isinstance(data, list) and len(data) > 0:
            if 'result' in data[0]:
                return [row['result'] for row in data]

        return data

    def _filter_sensitive_columns(
        self,
        data: List[Dict[str, Any]],
        user_role: str
    ) -> List[Dict[str, Any]]:
        """
        Remove sensitive columns based on user role

        Args:
            data: Query results
            user_role: User's role

        Returns:
            Filtered data
        """
        if user_role in ['admin', 'manager']:
            # Full access
            return data

        # Define sensitive columns by role
        sensitive = {
            'guest': ['email', 'phone', 'password', 'first_name', 'last_name'],
            'viewer': ['email', 'phone', 'password'],
            'engineer': ['password']
        }

        blocked = sensitive.get(user_role, [])

        if not blocked:
            return data

        # Filter out sensitive columns
        return [
            {k: ('[Hidden]' if k in blocked else v) for k, v in row.items()}
            for row in data
        ]

    def _generate_empty_message(self, user_query: str, entity: str, personalized: bool) -> str:
        """
        Generate context-aware message when no data found

        Args:
            user_query: Original query
            entity: Entity type (projects, tasks, etc.)
            personalized: Whether query was personalized

        Returns:
            User-friendly message explaining why no data
        """
        entity_names = {
            'projects': 'проектов',
            'stages': 'этапов',
            'objects': 'объектов',
            'sections': 'разделов',
            'tasks': 'задач',
            'profiles': 'сотрудников',
            'view_employee_workloads': 'данных о загрузке',
            'v_budgets_full': 'данных о бюджете',
            'view_project_dashboard': 'данных о часах',
            'view_planning_analytics_summary': 'аналитических данных',
            'view_my_work_analytics': 'данных о вашей работе'
        }

        entity_name = entity_names.get(entity, 'данных')

        if personalized:
            if entity == 'projects':
                return f"По запросу '{user_query}' не найдено ваших {entity_name}. Возможно, вы не назначены менеджером ни на одном проекте."
            elif entity == 'tasks':
                return f"По запросу '{user_query}' не найдено ваших {entity_name}. Возможно, вам не назначены задачи."
            elif entity == 'objects':
                return f"По запросу '{user_query}' не найдено ваших {entity_name}. Возможно, вы не назначены ответственным ни на одном объекте."
            elif entity == 'sections':
                return f"По запросу '{user_query}' не найдено ваших {entity_name}. Возможно, вы не ответственный ни на одном разделе."
            elif entity == 'stages':
                return f"По запросу '{user_query}' не найдено ваших {entity_name}. Возможно, нет этапов с объектами, где вы ответственный."
            else:
                return f"По запросу '{user_query}' не найдено ваших {entity_name}."
        else:
            if entity == 'view_employee_workloads':
                return f"По запросу '{user_query}' не найдено {entity_name}. Возможно, данные о планировании еще не внесены."
            else:
                return f"По запросу '{user_query}' не найдено {entity_name}."

    def _is_data_empty(self, data: List[Dict[str, Any]]) -> bool:
        """
        Check if data contains only None values (empty view)

        Args:
            data: Query results

        Returns:
            True if all non-id values are None
        """
        if not data:
            return True

        # Check if all values (except IDs) are None
        for row in data:
            # Get non-id values
            values = [v for k, v in row.items() if 'id' not in k.lower() and 'name' not in k.lower()]
            # If any non-None value exists, data is not empty
            if any(v is not None for v in values):
                return False

        return True

    def _prepare_table_data(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Prepare table data in frontend-friendly format

        Args:
            data: Query results as list of dicts

        Returns:
            Dict with columns and rows structure
        """
        if not data:
            return {"columns": [], "rows": []}

        # Extract column names from first row, filter out ID columns
        all_columns = list(data[0].keys())
        columns = [
            col for col in all_columns
            if not (col.endswith('_id') or col == 'id')
        ]

        # Convert list of dicts to list of lists (only non-ID columns)
        rows = [[row.get(col) for col in columns] for row in data]

        return {
            "columns": columns,
            "rows": rows
        }

    def _prepare_chart_data(
        self,
        data: List[Dict[str, Any]],
        chart_type: str
    ) -> Dict[str, Any]:
        """
        Prepare chart configuration for frontend (Chart.js)

        Args:
            data: Query results
            chart_type: Type of chart

        Returns:
            Chart.js config
        """
        if chart_type == "pie":
            return {
                "type": "pie",
                "data": {
                    "labels": [row.get("label", row.get("name", "Unknown")) for row in data],
                    "datasets": [{
                        "data": [row.get("value", row.get("count", 0)) for row in data],
                        "backgroundColor": [
                            "#FF6384", "#36A2EB", "#FFCE56", "#4BC0C0", "#9966FF"
                        ]
                    }]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "legend": {"position": "bottom"}
                    }
                }
            }
        elif chart_type == "bar":
            return {
                "type": "bar",
                "data": {
                    "labels": [row.get("label", row.get("name", "")) for row in data],
                    "datasets": [{
                        "label": "Значение",
                        "data": [row.get("value", row.get("count", 0)) for row in data],
                        "backgroundColor": "#36A2EB"
                    }]
                },
                "options": {
                    "responsive": True,
                    "scales": {
                        "y": {"beginAtZero": True}
                    }
                }
            }
        elif chart_type == "line":
            return {
                "type": "line",
                "data": {
                    "labels": [row.get("date", row.get("label", "")) for row in data],
                    "datasets": [{
                        "label": "Динамика",
                        "data": [row.get("value", 0) for row in data],
                        "borderColor": "#36A2EB",
                        "fill": False
                    }]
                },
                "options": {
                    "responsive": True,
                    "scales": {
                        "y": {"beginAtZero": True}
                    }
                }
            }
        elif chart_type == "area":
            return {
                "type": "area",
                "data": {
                    "labels": [row.get("date", row.get("label", "")) for row in data],
                    "datasets": [{
                        "label": "Объём",
                        "data": [row.get("value", 0) for row in data],
                        "borderColor": "#36A2EB",
                        "backgroundColor": "rgba(54, 162, 235, 0.3)",
                        "fill": True
                    }]
                },
                "options": {
                    "responsive": True,
                    "scales": {
                        "y": {"beginAtZero": True}
                    }
                }
            }
        elif chart_type == "radar":
            return {
                "type": "radar",
                "data": {
                    "labels": [row.get("label", row.get("name", "")) for row in data],
                    "datasets": [{
                        "label": "Показатели",
                        "data": [row.get("value", row.get("progress", 0)) for row in data],
                        "borderColor": "#36A2EB",
                        "backgroundColor": "rgba(54, 162, 235, 0.2)"
                    }]
                },
                "options": {
                    "responsive": True,
                    "scales": {
                        "r": {"beginAtZero": True, "max": 100}
                    }
                }
            }
        elif chart_type == "radialBar":
            return {
                "type": "radialBar",
                "data": {
                    "labels": [row.get("label", row.get("name", row.get("project_name", ""))) for row in data],
                    "datasets": [{
                        "label": "Прогресс",
                        "data": [row.get("value", row.get("progress", row.get("avg_progress", 0))) for row in data]
                    }]
                },
                "options": {
                    "responsive": True,
                    "max": 100
                }
            }
        else:
            return {}

    def _get_chart_title(self, query: AnalyticsQuery) -> str:
        """Generate chart title based on query"""
        entity_names = {
            'projects': 'Проекты',
            'stages': 'Этапы',
            'objects': 'Объекты',
            'sections': 'Разделы',
            'tasks': 'Задачи',
            'profiles': 'Сотрудники',
            'view_employee_workloads': 'Загрузка сотрудников',
            'v_budgets_full': 'Бюджеты'
        }

        entity = query.entities[0] if query.entities else 'projects'
        entity_name = entity_names.get(entity, entity)

        if query.chart_type == 'radialBar':
            return f"Прогресс: {entity_name}"
        elif query.chart_type == 'pie':
            return f"Распределение: {entity_name}"
        elif query.chart_type == 'bar':
            return f"Сравнение: {entity_name}"
        elif query.chart_type == 'line':
            return f"Динамика: {entity_name}"
        else:
            return entity_name

    def process_analytics(
        self,
        user_query: str,
        user_role: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> AnalyticsResult:
        """
        Main analytics processing pipeline with RBAC support

        Args:
            user_query: Natural language query
            user_role: User role for RBAC filtering
            user_id: User ID for personalized queries

        Returns:
            AnalyticsResult with data and visualization config
        """
        logger.info(f"📊 ANALYTICS: query='{user_query}', role={user_role}, user_id={user_id}")

        try:
            # Step 1: Parse natural language to structured query
            parsed_query = self._parse_user_query(user_query, user_role)

            # Step 2: Generate SQL with RBAC
            sql = self._generate_sql(parsed_query, user_role, user_id)

            # Step 3: Execute SQL with retry
            data = self._execute_sql(sql, user_role or 'guest')

            # Check if data is empty or contains only None values
            if not data or self._is_data_empty(data):
                # Generate context-aware empty message
                entity = parsed_query.entities[0] if parsed_query.entities else 'проекты'
                empty_message = self._generate_empty_message(user_query, entity, parsed_query.personalized)

                return AnalyticsResult(
                    type="text",
                    content=empty_message,
                    sql_query=sql,
                    metadata={"row_count": 0, "empty_data": True}
                )

            # Step 4: Determine result type
            # Special handling for workload queries - return analytics, not table
            if parsed_query.entities and 'view_employee_workloads' in parsed_query.entities:
                # Return text analysis with insights
                summary = self._generate_workload_analysis(data, user_query)
                return AnalyticsResult(
                    type="text",
                    content=summary,
                    sql_query=sql,
                    metadata={"row_count": len(data)}
                )
            elif parsed_query.chart_type and parsed_query.chart_type != 'table':
                # Return chart data (pie, bar, line, area, radar, radialBar)
                logger.info(f"Chart data (first 3): {json.dumps(data[:3] if data else [], ensure_ascii=False, default=str)}")

                # Determine data keys for frontend
                x_key = "label" if data and "label" in data[0] else "name"
                y_keys = ["value"] if data and "value" in data[0] else ["count"]

                # Format content as expected by frontend ChartWidget
                chart_content = {
                    "chartType": parsed_query.chart_type,
                    "data": data,
                    "xKey": x_key,
                    "yKeys": y_keys,
                    "title": self._get_chart_title(parsed_query),
                    "valueSuffix": "%" if parsed_query.chart_type == "radialBar" else ""
                }

                return AnalyticsResult(
                    type="chart",
                    content=chart_content,
                    sql_query=sql,
                    metadata={"row_count": len(data)}
                )
            elif parsed_query.intent == "statistics":
                # Return text summary
                summary = self._generate_summary(data, parsed_query)
                return AnalyticsResult(
                    type="text",
                    content=summary,
                    sql_query=sql,
                    metadata={"row_count": len(data)}
                )
            else:
                # Return table (including when chart_type='table')
                table_data = self._prepare_table_data(data)
                return AnalyticsResult(
                    type="table",
                    content=table_data,
                    sql_query=sql,
                    metadata={"row_count": len(data)}
                )

        except Exception as e:
            logger.error(f"Analytics processing error: {e}")
            return AnalyticsResult(
                type="text",
                content=f"Произошла ошибка при обработке аналитического запроса: {str(e)}",
                metadata={"error": str(e)}
            )

    def _generate_workload_analysis(self, data: List[Dict[str, Any]], user_query: str) -> str:
        """
        Generate workload analysis with insights

        Args:
            data: Workload data from view_employee_workloads
            user_query: Original user query

        Returns:
            Analytical text summary in Russian
        """
        if not data:
            return "Данных о загрузке сотрудников не найдено."

        # Filter out rows with None loading_rate
        workload_data = [row for row in data if row.get('loading_rate') is not None]

        if not workload_data:
            return "В данный момент нет активной загрузки у сотрудников. Возможно, данные о планировании еще не внесены."

        # Analyze workload
        loading_rates = [row['loading_rate'] for row in workload_data]
        avg_load = sum(loading_rates) / len(loading_rates)

        overloaded = [row for row in workload_data if row['loading_rate'] > 100]
        high_load = [row for row in workload_data if 80 <= row['loading_rate'] <= 100]
        normal_load = [row for row in workload_data if 50 <= row['loading_rate'] < 80]
        low_load = [row for row in workload_data if row['loading_rate'] < 50]

        # Build analysis
        analysis = f"📊 **Анализ загрузки сотрудников**\n\n"
        analysis += f"Всего сотрудников с активной загрузкой: {len(workload_data)}\n"
        analysis += f"Средняя загрузка: {avg_load:.1f}%\n\n"

        if overloaded:
            analysis += f"⚠️ **Перегружены ({len(overloaded)} чел.):**\n"
            for row in overloaded[:5]:  # Top 5
                analysis += f"- {row['full_name']}: {row['loading_rate']}% ({row.get('project_name', 'N/A')})\n"
            if len(overloaded) > 5:
                analysis += f"... и еще {len(overloaded) - 5} человек\n"
            analysis += "\n"

        if high_load:
            analysis += f"🔶 **Высокая загрузка ({len(high_load)} чел.):** 80-100%\n\n"

        if normal_load:
            analysis += f"✅ **Нормальная загрузка ({len(normal_load)} чел.):** 50-80%\n\n"

        if low_load:
            analysis += f"📉 **Низкая загрузка ({len(low_load)} чел.):** <50%\n\n"

        # Recommendations
        if overloaded:
            analysis += "💡 **Рекомендации:**\n"
            analysis += "- Перераспределить задачи перегруженных сотрудников\n"
            analysis += "- Привлечь дополнительные ресурсы к проектам\n"

        return analysis

    def _generate_summary(self, data: List[Dict[str, Any]], query: AnalyticsQuery) -> str:
        """Generate text summary from data"""
        if not data:
            return "Данные не найдены."

        # Use LLM to generate natural language summary
        data_str = json.dumps(data, ensure_ascii=False, indent=2)
        prompt = f"""На основе следующих данных создай краткий аналитический отчет на русском языке:

Запрос: {query.intent} по {', '.join(query.entities)}
Данные:
{data_str}

Создай структурированный отчет с ключевыми выводами."""

        try:
            summary = self.invoke(prompt)
            return summary
        except Exception as e:
            logger.error(f"Summary generation error: {e}")
            return f"Найдено записей: {len(data)}"

    def answer_question(self, question: str, user_role: Optional[str] = None) -> str:
        """
        Process analytics question (for orchestrator compatibility)

        Args:
            question: User question
            user_role: User role for RBAC

        Returns:
            Answer as string (may include JSON for structured data)
        """
        result = self.process_analytics(question, user_role)

        # Return as JSON for orchestrator to parse
        return json.dumps(result.model_dump(), ensure_ascii=False, indent=2)

    def process_message(self, user_message: str, user_role: Optional[str] = None) -> str:
        """Alias for answer_question"""
        return self.answer_question(user_message, user_role)


class CircuitBreaker:
    """
    Circuit breaker pattern for SQL execution protection

    Prevents cascading failures by stopping requests when error rate is too high.
    States: closed (normal), open (blocking), half_open (testing recovery)
    """

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        """
        Initialize circuit breaker

        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before attempting recovery
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'closed'  # closed, open, half_open

    def is_open(self) -> bool:
        """
        Check if circuit is open (blocking requests)

        Returns:
            True if circuit is open
        """
        if self.state == 'open':
            # Try to recover after timeout
            if time.time() - self.last_failure_time > self.recovery_timeout:
                logger.info("Circuit breaker: transitioning to HALF-OPEN")
                self.state = 'half_open'
                return False
            return True
        return False

    def record_success(self):
        """Record successful execution - reset failure count"""
        if self.state == 'half_open':
            logger.info("Circuit breaker: CLOSED (recovered)")
        self.state = 'closed'
        self.failure_count = 0

    def record_failure(self):
        """Record failed execution - increment failure count"""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            logger.error(
                f"Circuit breaker: OPEN (threshold reached: {self.failure_count})"
            )
            self.state = 'open'
