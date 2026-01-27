"""
Pydantic models for Analytics Agent

Shared models used by both analytics_agent.py and sql_generator.py
to avoid circular imports.
"""

from typing import Dict, Any, List, Optional, Literal, Union
from pydantic import BaseModel, Field, ConfigDict


class FilterOptions(BaseModel):
    """Filter options for analytics queries"""
    model_config = ConfigDict(extra="forbid")  # Strict schema for OpenAI structured output

    status: Optional[str] = Field(None, description="Filter by status (active, completed, etc.)")
    date_range: Optional[str] = Field(None, description="Date range filter (last_week, last_month, etc.)")
    responsible: Optional[str] = Field(None, description="Filter by responsible person ID")
    department: Optional[str] = Field(None, description="Filter by department")
    project_id: Optional[str] = Field(None, description="Filter by specific project ID")
    start_date: Optional[str] = Field(None, description="Start date for date range (ISO format)")
    end_date: Optional[str] = Field(None, description="End date for date range (ISO format)")
    entity: Optional[str] = Field(None, description="Entity type (projects, stages, objects, sections)")

    # Numeric filters for budget, hours, etc.
    min_budget: Optional[float] = Field(None, description="Minimum budget amount")
    max_budget: Optional[float] = Field(None, description="Maximum budget amount")
    min_hours: Optional[float] = Field(None, description="Minimum hours")
    max_hours: Optional[float] = Field(None, description="Maximum hours")
    min_progress: Optional[int] = Field(None, description="Minimum progress percentage")
    max_progress: Optional[int] = Field(None, description="Maximum progress percentage")


class AnalyticsQuery(BaseModel):
    """Structured analytics query"""
    intent: Literal["report", "chart", "statistics", "sql_query", "comparison", "complex_join", "ranking"] = Field(
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
    chart_type: Optional[Literal["bar", "line", "pie", "area", "radar", "radialBar", "table"]] = Field(
        None,
        description="Type of visualization: line (trends), bar (categories), area (volume), pie (shares), radar (multi-dimensional), radialBar (progress/ratings), table"
    )
    personalized: bool = Field(
        default=False,
        description="Whether query is personalized (e.g., 'my projects', 'my tasks')"
    )
    require_all_entities: bool = Field(
        default=False,
        description="If true, use INNER JOIN (only rows with all entities). If false, use LEFT JOIN (all primary entity rows)"
    )
    requested_columns: List[str] = Field(
        default_factory=list,
        description="Specific columns requested by user (e.g., ['name', 'status', 'first_name', 'last_name']). Empty list = auto-select minimal columns"
    )
    limit: Optional[int] = Field(
        None,
        description="Limit number of results (for TOP N queries)"
    )
    order_by: Optional[str] = Field(
        None,
        description="Column to order by (e.g., 'count', 'total_amount', 'progress')"
    )
    order_direction: Optional[Literal["asc", "desc"]] = Field(
        "desc",
        description="Order direction (asc or desc)"
    )
    group_by_entity: Optional[str] = Field(
        None,
        description="Entity to group by (e.g., 'profiles' for 'group by manager')"
    )
    exclude_related: bool = Field(
        default=False,
        description="If true, use LEFT JOIN + WHERE related.id IS NULL (find entities WITHOUT related records). Use for queries like 'employees without tasks', 'projects without budget'"
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
