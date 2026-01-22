"""
Pydantic models for Analytics Agent

Shared models used by both analytics_agent.py and sql_generator.py
to avoid circular imports.
"""

from typing import Dict, Any, List, Optional, Literal, Union
from pydantic import BaseModel, Field, ConfigDict


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
    entity: Optional[str] = Field(None, description="Entity type (projects, stages, objects, sections)")


class AnalyticsQuery(BaseModel):
    """Structured analytics query"""
    intent: Literal["report", "chart", "statistics", "sql_query", "comparison", "complex_join"] = Field(
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
    personalized: bool = Field(
        default=False,
        description="Whether query is personalized (e.g., 'my projects', 'my tasks')"
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
