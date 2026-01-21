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
1. intent: тип операции (report, chart, statistics, sql_query, comparison)
2. entities: какие сущности затрагивает запрос (projects, users, stages, objects)
3. metrics: какие метрики нужны (count, sum, avg, progress, status_distribution)
4. filters: какие фильтры применить (date_range, status, department, responsible)
5. aggregation: группировка (daily, weekly, monthly, by_user, by_project)
6. chart_type: тип визуализации (bar, line, pie, table, mixed)

Примеры:
- "Покажи количество проектов по статусам" → intent=chart, entities=[projects], metrics=[count], chart_type=pie
- "Статистика завершенных объектов за последний месяц" → intent=statistics, entities=[objects], filters={{status: completed, date_range: last_month}}
- "Сравни прогресс проектов" → intent=comparison, entities=[projects], metrics=[progress]
"""

        try:
            parsed = self.query_llm.invoke(prompt)
            logger.info(f"Parsed query: {parsed}")
            return parsed
        except Exception as e:
            logger.error(f"Error parsing query: {e}")
            # Fallback to simple query
            return AnalyticsQuery(
                intent="report",
                entities=["projects"],
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

        # Extract column names from first row
        columns = list(data[0].keys())

        # Convert list of dicts to list of lists
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
        else:
            return {}

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

            # Step 4: Determine result type
            if parsed_query.chart_type and parsed_query.chart_type != 'table':
                # Return chart data (pie, bar, line, mixed)
                chart_config = self._prepare_chart_data(data, parsed_query.chart_type)
                return AnalyticsResult(
                    type="chart",
                    content=data,
                    sql_query=sql,
                    chart_config=chart_config,
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
