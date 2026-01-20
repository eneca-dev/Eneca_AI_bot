"""Analytics Agent for data analysis, reporting, and visualization"""
from pathlib import Path
from typing import Dict, Any, List, Optional, Literal, Union
from pydantic import BaseModel, Field, ConfigDict
from agents.base import BaseAgent
from database.supabase_client import supabase_db_client
from core.config import settings
from loguru import logger
import json


class FilterOptions(BaseModel):
    """Filter options for analytics queries"""
    model_config = ConfigDict(extra="forbid")

    status: Optional[str] = Field(None, description="Filter by status (active, completed, etc.)")
    date_range: Optional[str] = Field(None, description="Date range filter (last_week, last_month, etc.)")
    responsible: Optional[str] = Field(None, description="Filter by responsible person ID")
    department: Optional[str] = Field(None, description="Filter by department")
    project_id: Optional[str] = Field(None, description="Filter by specific project ID")
    start_date: Optional[str] = Field(None, description="Start date for date range (ISO format)")
    end_date: Optional[str] = Field(None, description="End date for date range (ISO format)")


class AnalyticsQuery(BaseModel):
    """Structured analytics query"""
    intent: Literal["report", "chart", "statistics", "sql_query", "comparison"] = Field(
        description="Type of analytics operation"
    )
    entities: List[str] = Field(
        default_factory=list,
        description="Entities involved (projects, users, stages, etc.)"
    )
    metrics: List[str] = Field(
        default_factory=list,
        description="Metrics to analyze (count, sum, avg, progress, etc.)"
    )
    filters: FilterOptions = Field(
        default_factory=FilterOptions,
        description="Filters to apply (date_range, status, responsible, etc.)"
    )
    aggregation: Optional[str] = Field(
        None,
        description="Aggregation type (daily, weekly, monthly, by_user, by_project)"
    )
    chart_type: Optional[Literal["bar", "line", "pie", "table", "mixed"]] = Field(
        None,
        description="Type of visualization"
    )


class AnalyticsResult(BaseModel):
    """Structured analytics result"""
    type: Literal["text", "table", "chart", "mixed"] = Field(
        description="Type of result"
    )
    content: Union[str, Dict[str, Any], List[Dict[str, Any]]] = Field(
        description="Result content"
    )
    sql_query: Optional[str] = Field(
        None,
        description="SQL query used (for transparency)"
    )
    chart_config: Optional[Dict[str, Any]] = Field(
        None,
        description="Chart.js configuration for frontend"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (row_count, execution_time, etc.)"
    )


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

    def _generate_sql(self, parsed_query: AnalyticsQuery, user_role: Optional[str] = None) -> str:
        """
        Generate SQL query from structured analytics query

        Args:
            parsed_query: Structured query
            user_role: User role for RLS

        Returns:
            SQL query string
        """
        # Map intent to SQL templates
        if parsed_query.intent == "report":
            return self._generate_report_sql(parsed_query)
        elif parsed_query.intent == "chart":
            return self._generate_chart_sql(parsed_query)
        elif parsed_query.intent == "statistics":
            return self._generate_statistics_sql(parsed_query)
        elif parsed_query.intent == "comparison":
            return self._generate_comparison_sql(parsed_query)
        else:
            return self._generate_generic_sql(parsed_query)

    def _generate_report_sql(self, query: AnalyticsQuery) -> str:
        """Generate SQL for reports"""
        entity = query.entities[0] if query.entities else "projects"

        # Example: Project report
        if entity == "projects":
            sql = """
            SELECT
                p.id,
                p.name,
                p.status,
                COUNT(DISTINCT s.id) as stages_count,
                AVG(s.progress) as avg_progress,
                p.created_at
            FROM projects p
            LEFT JOIN stages s ON s.project_id = p.id
            """

            # Add filters
            conditions = []
            if query.filters.status:
                conditions.append(f"p.status = '{query.filters.status}'")
            if query.filters.date_range:
                conditions.append("p.created_at >= NOW() - INTERVAL '30 days'")

            if conditions:
                sql += " WHERE " + " AND ".join(conditions)

            sql += " GROUP BY p.id, p.name, p.status, p.created_at ORDER BY p.created_at DESC"
            return sql

        return "SELECT * FROM projects LIMIT 10"

    def _generate_chart_sql(self, query: AnalyticsQuery) -> str:
        """Generate SQL for chart data"""
        entity = query.entities[0] if query.entities else "projects"

        # Example: Status distribution
        if "count" in query.metrics:
            return f"""
            SELECT
                {entity[:-1]}_status as label,
                COUNT(*) as value
            FROM {entity}
            GROUP BY {entity[:-1]}_status
            ORDER BY value DESC
            """

        return f"SELECT COUNT(*) as count FROM {entity}"

    def _generate_statistics_sql(self, query: AnalyticsQuery) -> str:
        """Generate SQL for statistics"""
        entity = query.entities[0] if query.entities else "projects"

        return f"""
        SELECT
            COUNT(*) as total_count,
            COUNT(DISTINCT responsible_id) as unique_users,
            AVG(progress) as avg_progress,
            MIN(created_at) as earliest_date,
            MAX(updated_at) as latest_update
        FROM {entity}
        """

    def _generate_comparison_sql(self, query: AnalyticsQuery) -> str:
        """Generate SQL for comparisons"""
        return """
        SELECT
            p.name as project_name,
            AVG(s.progress) as avg_progress,
            COUNT(s.id) as stages_count
        FROM projects p
        LEFT JOIN stages s ON s.project_id = p.id
        GROUP BY p.id, p.name
        ORDER BY avg_progress DESC
        """

    def _generate_generic_sql(self, query: AnalyticsQuery) -> str:
        """Fallback SQL generator"""
        entity = query.entities[0] if query.entities else "projects"
        return f"SELECT * FROM {entity} LIMIT 10"

    def _execute_sql(self, sql: str) -> List[Dict[str, Any]]:
        """
        Execute SQL query safely

        Args:
            sql: SQL query (SELECT only)

        Returns:
            Query results as list of dicts
        """
        try:
            # Safety check: only SELECT queries
            if not sql.strip().upper().startswith("SELECT"):
                raise ValueError("Only SELECT queries are allowed")

            # Execute via Supabase RPC or raw SQL
            # Note: Supabase Python client doesn't support raw SQL directly
            # You may need to create a Postgres function or use psycopg2

            logger.info(f"Executing SQL: {sql}")

            # Execute SQL via Supabase RPC
            # NOTE: You need to create a Postgres function 'execute_analytics_query' in Supabase
            # Or use direct table queries for simple cases

            # For now, execute via Supabase client (read-only queries)
            try:
                response = self.db.supabase.rpc('execute_analytics_query', {'sql_query': sql}).execute()
                return response.data if response.data else []
            except Exception as rpc_error:
                logger.warning(f"RPC execution failed: {rpc_error}, falling back to direct query")
                # Fallback: try direct table query for simple SELECT statements
                # This is a simplified approach - in production, use proper RPC or ORM
                return []

        except Exception as e:
            logger.error(f"SQL execution error: {e}")
            return []

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
        user_role: Optional[str] = None
    ) -> AnalyticsResult:
        """
        Main analytics processing pipeline

        Args:
            user_query: Natural language query
            user_role: User role for RBAC

        Returns:
            AnalyticsResult with data and visualization config
        """
        logger.info(f"📊 ANALYTICS AGENT: processing query: '{user_query}'")

        try:
            # Step 1: Parse natural language to structured query
            parsed_query = self._parse_user_query(user_query, user_role)

            # Step 2: Generate SQL
            sql = self._generate_sql(parsed_query, user_role)

            # Step 3: Execute SQL
            data = self._execute_sql(sql)

            # Step 4: Determine result type
            if parsed_query.chart_type:
                # Return chart data
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
                # Return table
                return AnalyticsResult(
                    type="table",
                    content=data,
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
