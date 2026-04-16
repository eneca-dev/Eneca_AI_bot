"""
SQL Generator for Analytics Agent

Generates safe, schema-aware SQL queries for all entities with RBAC filtering.
Supports auto-JOIN generation, parameter escaping, and SQL injection protection.
"""

from typing import Dict, List, Tuple, Optional, Any
from loguru import logger

# Import models from shared module to avoid circular import
from agents.analytics_models import AnalyticsQuery, FilterOptions


class SQLGenerator:
    """Universal SQL generator with schema awareness and RBAC support"""

    # Database schema definition for all entities
    SCHEMA = {
        'projects': {
            'table': 'projects',
            'alias': 'p',
            'columns': [
                'project_id', 'project_name', 'project_status', 'project_description',
                'project_manager', 'project_lead_engineer', 'project_created', 'project_updated',
                'client_id', 'external_id', 'external_source', 'stage_type'
            ],
            'relations': {
                'stages': ('stages', 'project_id', 'project_id'),
                'manager': ('profiles', 'project_manager', 'user_id'),
                'budget': ('v_budgets_full', 'project_id', 'entity_id')
            },
            'group_by_column': 'project_status',
            'label_column': 'project_name',
            'value_column': 'project_id'
        },
        'stages': {
            'table': 'stages',
            'alias': 's',
            'columns': [
                'stage_id', 'stage_project_id', 'stage_name', 'stage_description',
                'stage_created', 'stage_updated', 'external_id', 'external_source'
            ],
            'relations': {
                'project': ('projects', 'stage_project_id', 'project_id'),
                'objects': ('objects', 'stage_id', 'object_stage_id')
            },
            'group_by_column': 'stage_project_id',
            'label_column': 'stage_name',
            'value_column': 'stage_id'
        },
        'objects': {
            'table': 'objects',
            'alias': 'o',
            'columns': [
                'object_id', 'object_stage_id', 'object_name', 'object_description',
                'object_responsible', 'object_start_date', 'object_end_date',
                'object_created', 'object_updated', 'object_project_id'
            ],
            'relations': {
                'stage': ('stages', 'object_stage_id', 'stage_id'),
                'responsible': ('profiles', 'object_responsible', 'user_id'),
                'sections': ('sections', 'object_id', 'section_object_id'),
                'project': ('projects', 'object_project_id', 'project_id')
            },
            'group_by_column': 'object_responsible',
            'label_column': 'object_name',
            'value_column': 'object_id'
        },
        'sections': {
            'table': 'sections',
            'alias': 'sec',
            'columns': [
                'section_id', 'section_object_id', 'section_name', 'section_description',
                'section_responsible', 'section_status_id', 'section_project_id',
                'section_start_date', 'section_end_date', 'section_created', 'section_updated'
            ],
            'relations': {
                'object': ('objects', 'section_object_id', 'object_id')
            },
            'group_by_column': 'section_status_id',
            'label_column': 'section_name',
            'value_column': 'section_id'
        },
        'profiles': {
            'table': 'profiles',
            'alias': 'u',
            'columns': [
                'user_id', 'email', 'first_name', 'last_name',
                'position_id', 'department_id', 'team_id', 'created_at'
            ],
            'relations': {
                'assigned_tasks': ('tasks', 'user_id', 'task_responsible')
            },
            'group_by_column': 'department_id',
            'label_column': 'first_name',
            'value_column': 'user_id'
        },
        'view_employee_workloads': {
            'table': 'view_employee_workloads',
            'alias': 'w',
            'columns': [
                'user_id', 'full_name', 'project_name', 'section_name',
                'loading_rate', 'loading_start', 'loading_finish'
            ],
            'relations': {},
            'group_by_column': 'loading_rate',
            'label_column': 'full_name',
            'value_column': 'loading_rate'
        },
        'v_budgets_full': {
            'table': 'v_budgets_full',
            'alias': 'b',
            'columns': [
                'budget_id', 'entity_id', 'entity_type',
                'total_amount', 'total_spent', 'remaining_amount', 'spent_percentage'
            ],
            'relations': {},
            'group_by_column': 'entity_type',
            'label_column': 'entity_id',
            'value_column': 'total_amount'
        },
        'view_project_dashboard': {
            'table': 'view_project_dashboard',
            'alias': 'pd',
            'columns': [
                'project_id', 'hours_planned_total', 'hours_actual_total'
            ],
            'relations': {},
            'group_by_column': 'project_id',
            'label_column': 'project_id',
            'value_column': 'hours_planned_total'
        },
        'view_planning_analytics_summary': {
            'table': 'view_planning_analytics_summary',
            'alias': 'pas',
            'columns': [
                'analytics_date', 'projects_in_work_today', 'avg_department_loading'
            ],
            'relations': {},
            'group_by_column': 'analytics_date',
            'label_column': 'analytics_date',
            'value_column': 'projects_in_work_today'
        },
        'view_my_work_analytics': {
            'table': 'view_my_work_analytics',
            'alias': 'mwa',
            'columns': [
                'user_id', 'week_hours', 'comments_count'
            ],
            'relations': {},
            'group_by_column': 'user_id',
            'label_column': 'user_id',
            'value_column': 'week_hours'
        },
        'tasks': {
            'table': 'tasks',
            'alias': 't',
            'columns': [
                'task_id', 'task_parent_section', 'task_name', 'task_description',
                'task_responsible', 'task_status', 'task_created', 'task_updated',
                'task_start_date', 'task_end_date'
            ],
            'relations': {
                'section': ('sections', 'task_parent_section', 'section_id'),
                'responsible': ('profiles', 'task_responsible', 'user_id')
            },
            'group_by_column': 'task_status',
            'label_column': 'task_name',
            'value_column': 'task_id'
        }
    }

    def _get_column_name(self, entity: str, logical_name: str) -> str:
        """
        Get actual column name from schema based on logical name

        Args:
            entity: Entity name (projects, stages, objects, etc.)
            logical_name: Logical column name (status, created_at, updated_at, id, name)

        Returns:
            Actual column name from schema
        """
        schema = self.SCHEMA.get(entity, self.SCHEMA['projects'])

        # Known mapping for projects table (confirmed by user's data)
        if entity == 'projects':
            mapping = {
                'id': 'project_id',
                'name': 'project_name',
                'status': 'project_status',
                'description': 'project_description',
                'created_at': 'project_created',
                'updated_at': 'project_updated',
                'manager': 'project_manager',
                'lead_engineer': 'project_lead_engineer'
            }
            return mapping.get(logical_name, logical_name)

        # Known mapping for stages table (prefixed)
        if entity == 'stages':
            mapping = {
                'id': 'stage_id',
                'name': 'stage_name',
                'description': 'stage_description',
                'project_id': 'stage_project_id',
                'created_at': 'stage_created',
                'updated_at': 'stage_updated'
            }
            return mapping.get(logical_name, logical_name)

        # Known mapping for sections table (prefixed)
        if entity == 'sections':
            mapping = {
                'id': 'section_id',
                'name': 'section_name',
                'description': 'section_description',
                'responsible': 'section_responsible',
                'responsible_id': 'section_responsible',
                'object_id': 'section_object_id',
                'project_id': 'section_project_id',
                'status_id': 'section_status_id',
                'start_date': 'section_start_date',
                'end_date': 'section_end_date',
                'created_at': 'section_created',
                'updated_at': 'section_updated'
            }
            return mapping.get(logical_name, logical_name)

        # Known mapping for tasks table (prefixed)
        if entity == 'tasks':
            mapping = {
                'id': 'task_id',
                'name': 'task_name',
                'description': 'task_description',
                'responsible': 'task_responsible',
                'responsible_id': 'task_responsible',
                'section_id': 'task_parent_section',
                'status': 'task_status',
                'start_date': 'task_start_date',
                'end_date': 'task_end_date',
                'created_at': 'task_created',
                'updated_at': 'task_updated'
            }
            return mapping.get(logical_name, logical_name)

        # Known mapping for objects table (prefixed like projects)
        if entity == 'objects':
            mapping = {
                'id': 'object_id',
                'name': 'object_name',
                'description': 'object_description',
                'responsible': 'object_responsible',
                'responsible_id': 'object_responsible',
                'stage_id': 'object_stage_id',
                'project_id': 'object_project_id',
                'start_date': 'object_start_date',
                'end_date': 'object_end_date',
                'created_at': 'object_created',
                'updated_at': 'object_updated'
            }
            return mapping.get(logical_name, logical_name)

        # Special mapping for view_employee_workloads
        if entity == 'view_employee_workloads':
            mapping = {
                'created_at': 'loading_start',  # Use loading_start for sorting
                'status': 'loading_rate',  # No status, use loading_rate instead
                'id': 'user_id',
                'name': 'full_name'
            }
            return mapping.get(logical_name, logical_name)

        # Special mapping for v_budgets_full
        if entity == 'v_budgets_full':
            mapping = {
                'created_at': 'budget_id',  # No created_at, use budget_id for sorting
                'status': 'entity_type',  # No status, use entity_type
                'id': 'budget_id',
                'name': 'entity_id'
            }
            return mapping.get(logical_name, logical_name)

        # Special mapping for view_project_dashboard
        if entity == 'view_project_dashboard':
            mapping = {
                'created_at': 'project_id',  # No created_at
                'status': 'project_id',  # No status
                'id': 'project_id',
                'name': 'project_id'
            }
            return mapping.get(logical_name, logical_name)

        # For other tables, check what's in SCHEMA columns list
        columns = schema.get('columns', [])

        # Strategy 1: Direct match (e.g., 'status' exists in columns)
        if logical_name in columns:
            return logical_name

        # Strategy 2: Try prefixed version (e.g., 'status' -> 'stage_status')
        # This handles if other tables also use prefixes like projects
        entity_singular = entity.rstrip('s')  # projects->project, stages->stage
        prefixed = f"{entity_singular}_{logical_name}"
        if prefixed in columns:
            return prefixed

        # Strategy 3: Fallback to original logical name
        # If SQL fails, error will guide us to fix SCHEMA
        return logical_name

    def generate_sql(
        self,
        parsed_query: AnalyticsQuery,
        user_role: str,
        user_id: Optional[str] = None
    ) -> Tuple[str, Dict]:
        """
        Main entry point for SQL generation

        Args:
            parsed_query: Parsed analytics query with intent, entities, filters
            user_role: User's role for RBAC filtering
            user_id: User's ID for personalized queries

        Returns:
            Tuple of (sql_string, parameters_dict)
        """
        logger.info(f"Generating SQL for intent='{parsed_query.intent}', entities={parsed_query.entities}")

        if parsed_query.intent == "complex_join":
            return self.generate_complex_join_sql(parsed_query, user_role, user_id)
        elif parsed_query.intent == "chart":
            return self.generate_chart_sql(parsed_query, user_role, user_id)
        elif parsed_query.intent == "report":
            return self.generate_report_sql(parsed_query, user_role, user_id)
        elif parsed_query.intent == "statistics":
            return self.generate_statistics_sql(parsed_query, user_role, user_id)
        elif parsed_query.intent == "comparison":
            return self.generate_comparison_sql(parsed_query, user_role, user_id)
        elif parsed_query.intent == "ranking":
            return self.generate_ranking_sql(parsed_query, user_role, user_id)
        else:
            return self.generate_generic_sql(parsed_query, user_role, user_id)

    def generate_complex_join_sql(
        self,
        query: AnalyticsQuery,
        user_role: str,
        user_id: Optional[str]
    ) -> Tuple[str, Dict]:
        """
        Generate SQL for complex queries with JOINs across multiple tables

        Args:
            query: Parsed query with multiple entities
            user_role: User role for RBAC
            user_id: User ID for personalization

        Returns:
            Tuple of (sql, params)
        """
        if not query.entities or len(query.entities) < 2:
            # Fallback to report if not enough entities
            return self.generate_report_sql(query, user_role, user_id)

        # Primary entity (first in list)
        primary_entity = query.entities[0]
        primary_schema = self.SCHEMA.get(primary_entity, self.SCHEMA['projects'])

        primary_alias = primary_schema['alias']
        primary_table = primary_schema['table']

        # Build SELECT clause based on requested_columns
        select_columns = []

        if query.requested_columns:
            # User explicitly requested specific columns
            for logical_col in query.requested_columns:
                # Determine which entity this column belongs to
                if logical_col in ['first_name', 'last_name', 'email']:
                    # Profile columns
                    if 'profiles' in query.entities:
                        related_alias = self.SCHEMA['profiles']['alias']
                        select_columns.append(f"{related_alias}.{logical_col}")
                elif logical_col in ['total_amount', 'spent', 'remaining', 'total_spent', 'remaining_amount']:
                    # Budget columns
                    if 'v_budgets_full' in query.entities:
                        budget_alias = self.SCHEMA['v_budgets_full']['alias']
                        # Map logical names to actual column names
                        col_map = {'spent': 'total_spent', 'remaining': 'remaining_amount'}
                        actual_col = col_map.get(logical_col, logical_col)
                        select_columns.append(f"{budget_alias}.{actual_col}")
                else:
                    # Primary entity columns
                    actual_col = self._get_column_name(primary_entity, logical_col)
                    select_columns.append(f"{primary_alias}.{actual_col}")
        else:
            # Auto-select: only name column by default
            name_col = self._get_column_name(primary_entity, 'name')
            select_columns.append(f"{primary_alias}.{name_col}")

        # Build JOINs and add columns from related entities
        joins = []
        for i, related_entity in enumerate(query.entities[1:], start=1):
            if related_entity not in self.SCHEMA:
                continue

            related_schema = self.SCHEMA[related_entity]
            related_alias = related_schema['alias']
            related_table = related_schema['table']

            # Find JOIN condition from relations
            join_condition = self._find_join_condition(
                primary_entity, primary_alias,
                related_entity, related_alias
            )

            if join_condition:
                # Choose JOIN type based on flags
                if query.exclude_related:
                    # LEFT JOIN for "without" queries (will filter NULL later)
                    join_type = "LEFT JOIN"
                elif query.require_all_entities:
                    # INNER JOIN for "with" queries
                    join_type = "INNER JOIN"
                else:
                    # LEFT JOIN for "and their" queries
                    join_type = "LEFT JOIN"

                joins.append(f"{join_type} {related_table} {related_alias} ON {join_condition}")

        # Build SQL
        select_clause = ",\n    ".join(select_columns) if select_columns else f"{primary_alias}.*"

        sql = f"""
SELECT
    {select_clause}
FROM {primary_table} {primary_alias}
"""

        # Add JOINs
        for join in joins:
            sql += join + "\n"

        sql += "WHERE 1=1\n"

        params = {}

        # For exclude_related queries, apply filters to related entity (not primary)
        if query.exclude_related and len(query.entities) > 1:
            # Apply filters to RELATED entity (e.g., tasks status, not profiles status)
            related_entity = query.entities[1]
            related_schema = self.SCHEMA.get(related_entity)
            if related_schema:
                related_alias = related_schema['alias']

                # Apply status/date filters to related entity
                sql, params = self._apply_filters(sql, params, query.filters, related_alias, related_entity)

                # Add IS NULL check to find entities WITHOUT related records
                related_id_col = self._get_column_name(related_entity, 'id')
                sql += f" AND {related_alias}.{related_id_col} IS NULL"
        else:
            # Normal query: apply filters on primary entity
            sql, params = self._apply_filters(sql, params, query.filters, primary_alias, primary_entity)

            # Apply filters on related entities (budget, hours, etc.)
            sql, params = self._apply_related_filters(sql, params, query.filters, query.entities)

        # Apply RBAC
        sql = self._apply_rbac_filter(sql, primary_entity, user_role, user_id, primary_alias)

        # Apply personalization if needed
        if query.personalized and user_id:
            sql, params = self._apply_personalization(sql, params, primary_entity, user_id, primary_alias)

        # Add ORDER BY
        created_col = self._get_column_name(primary_entity, 'created_at')
        sql += f"\nORDER BY {primary_alias}.{created_col} DESC"

        # Limit results
        sql += f"\nLIMIT 100"

        return sql, params

    def _find_join_condition(
        self,
        primary_entity: str,
        primary_alias: str,
        related_entity: str,
        related_alias: str
    ) -> Optional[str]:
        """
        Find JOIN condition between two entities based on SCHEMA relations

        Args:
            primary_entity: Primary table name (e.g., 'objects')
            primary_alias: Primary table alias (e.g., 'o')
            related_entity: Related table name (e.g., 'profiles')
            related_alias: Related table alias (e.g., 'u')

        Returns:
            JOIN condition string or None
        """
        primary_schema = self.SCHEMA.get(primary_entity)
        related_schema = self.SCHEMA.get(related_entity)

        if not primary_schema or not related_schema:
            return None

        # Strategy 1: Check primary → related relation
        for rel_name, (rel_table, fk, pk) in primary_schema.get('relations', {}).items():
            if rel_table == related_entity:
                return f"{related_alias}.{pk} = {primary_alias}.{fk}"

        # Strategy 2: Check related → primary relation (reverse)
        for rel_name, (rel_table, fk, pk) in related_schema.get('relations', {}).items():
            if rel_table == primary_entity:
                return f"{primary_alias}.{pk} = {related_alias}.{fk}"

        # Strategy 3: Common column name matching (fallback)
        # Try to find common foreign key patterns
        primary_cols = primary_schema.get('columns', [])
        related_cols = related_schema.get('columns', [])

        # Check if primary has FK to related (e.g., objects.responsible_id → profiles.user_id)
        if related_entity == 'profiles':
            for col in primary_cols:
                if 'responsible' in col.lower():
                    return f"{related_alias}.user_id = {primary_alias}.{col}"

        # Check for project_id links
        if related_entity == 'projects':
            if 'project_id' in primary_cols:
                return f"{related_alias}.project_id = {primary_alias}.project_id"

        # Check for stage_id links
        if related_entity == 'stages':
            if 'stage_id' in primary_cols:
                return f"{related_alias}.id = {primary_alias}.stage_id"

        # Special case: v_budgets_full needs entity_type filter
        if related_entity == 'v_budgets_full':
            if primary_entity == 'projects':
                # Budget for projects
                primary_id = self._get_column_name(primary_entity, 'id')
                return f"{related_alias}.entity_id = {primary_alias}.{primary_id} AND {related_alias}.entity_type = 'project'"
            elif primary_entity == 'stages':
                primary_id = self._get_column_name(primary_entity, 'id')
                return f"{related_alias}.entity_id = {primary_alias}.{primary_id} AND {related_alias}.entity_type = 'stage'"
            elif primary_entity == 'objects':
                primary_id = self._get_column_name(primary_entity, 'id')
                return f"{related_alias}.entity_id = {primary_alias}.{primary_id} AND {related_alias}.entity_type = 'object'"

        # No relation found
        return None

    def generate_chart_sql(
        self,
        query: AnalyticsQuery,
        user_role: str,
        user_id: Optional[str]
    ) -> Tuple[str, Dict]:
        """Generate SQL for chart visualization (pie, bar, line, area, radar, radialBar)"""

        entity = query.entities[0] if query.entities else 'projects'
        schema = self.SCHEMA.get(entity, self.SCHEMA['projects'])

        alias = schema['alias']
        table = schema['table']
        group_col = schema['group_by_column']
        name_col = self._get_column_name(entity, 'name')

        params = {}

        # Special handling for radialBar (progress/ratings)
        if query.chart_type == 'radialBar':
            # For radialBar we need individual items with progress values
            if 'progress' in query.metrics or entity in ['stages', 'objects', 'sections']:
                progress_col = self._get_column_name(entity, 'progress') if 'progress' in schema.get('columns', []) else None

                if progress_col:
                    sql = f"""
SELECT
    {alias}.{name_col} as label,
    COALESCE({alias}.{progress_col}, 0) as value
FROM {table} {alias}
WHERE 1=1
"""
                else:
                    # For entities without progress column, calculate completion rate based on status
                    status_col = self._get_column_name(entity, 'status')
                    sql = f"""
SELECT
    {alias}.{name_col} || ' (' || {alias}.{status_col} || ')' as label,
    CASE WHEN {alias}.{status_col} = 'completed' THEN 100
         WHEN {alias}.{status_col} = 'active' THEN 50
         ELSE 0 END as value,
    {alias}.{status_col} as status
FROM {table} {alias}
WHERE 1=1
"""
                # Apply filters and RBAC
                sql, params = self._apply_filters(sql, params, query.filters, alias, entity)
                sql = self._apply_rbac_filter(sql, entity, user_role, user_id, alias)
                sql += f"\nORDER BY value DESC"
                sql += f"\nLIMIT 10"
                return sql, params

        # Special handling for radar (multi-dimensional comparison)
        if query.chart_type == 'radar':
            sql = f"""
SELECT
    {alias}.{name_col} as label,
    COALESCE(AVG({alias}.{self._get_column_name(entity, 'progress') if 'progress' in schema.get('columns', []) else 'NULL'}), 0) as value
FROM {table} {alias}
WHERE 1=1
"""
            sql, params = self._apply_filters(sql, params, query.filters, alias, entity)
            sql = self._apply_rbac_filter(sql, entity, user_role, user_id, alias)
            sql += f"\nGROUP BY {alias}.{name_col}"
            sql += f"\nLIMIT 10"
            return sql, params

        # Default: pie, bar, line, area - group by column and count
        sql = f"""
SELECT
    {alias}.{group_col} as label,
    COUNT(*) as value
FROM {table} {alias}
WHERE 1=1
"""

        # Apply user filters
        sql, params = self._apply_filters(sql, params, query.filters, alias, entity)

        # Apply RBAC filtering
        sql = self._apply_rbac_filter(sql, entity, user_role, user_id, alias)

        sql += f"\nGROUP BY {alias}.{group_col}"
        sql += f"\nORDER BY value DESC"
        sql += f"\nLIMIT 20"

        return sql, params

    def generate_report_sql(
        self,
        query: AnalyticsQuery,
        user_role: str,
        user_id: Optional[str]
    ) -> Tuple[str, Dict]:
        """Generate SQL for detailed report"""

        entity = query.entities[0] if query.entities else 'projects'
        schema = self.SCHEMA.get(entity, self.SCHEMA['projects'])

        alias = schema['alias']
        table = schema['table']
        columns = schema['columns']

        # Build SELECT based on requested_columns
        if query.requested_columns:
            # User explicitly requested specific columns
            select_cols = []
            for logical_col in query.requested_columns:
                actual_col = self._get_column_name(entity, logical_col)
                # Skip UUID/ID columns
                if (actual_col.endswith('_id') or actual_col == 'id' or
                    actual_col.endswith('_responsible') or actual_col.endswith('_manager') or
                    actual_col == 'responsible' or actual_col == 'manager'):
                    continue
                select_cols.append(f"{alias}.{actual_col}")

            # If no valid columns after filtering, default to name
            if not select_cols:
                name_col = self._get_column_name(entity, 'name')
                select_cols.append(f"{alias}.{name_col}")
        else:
            # Default: only name column
            name_col = self._get_column_name(entity, 'name')
            select_cols = [f"{alias}.{name_col}"]

        sql = f"""
SELECT
    {', '.join(select_cols)}
FROM {table} {alias}
WHERE 1=1
"""

        params = {}

        # Apply filters
        sql, params = self._apply_filters(sql, params, query.filters, alias, entity)

        # Apply personalization (if query has "мои/мой/моя")
        if query.personalized and user_id:
            sql, params = self._apply_personalization(sql, params, entity, user_id, alias)

        # Apply RBAC
        sql = self._apply_rbac_filter(sql, entity, user_role, user_id, alias)

        # Use dynamic column name for created_at
        created_col = self._get_column_name(entity, 'created_at')
        sql += f"\nORDER BY {alias}.{created_col} DESC"
        sql += f"\nLIMIT 100"

        return sql, params

    def generate_statistics_sql(
        self,
        query: AnalyticsQuery,
        user_role: str,
        user_id: Optional[str]
    ) -> Tuple[str, Dict]:
        """Generate SQL for statistical aggregation"""

        entity = query.entities[0] if query.entities else 'projects'
        schema = self.SCHEMA.get(entity, self.SCHEMA['projects'])

        alias = schema['alias']
        table = schema['table']

        # Use dynamic column name for status
        status_col = self._get_column_name(entity, 'status')

        # Common statistics
        sql = f"""
SELECT
    COUNT(*) as total_count,
    COUNT(DISTINCT {alias}.{status_col}) as unique_statuses
"""

        # Add progress metrics if available
        if 'progress' in schema['columns']:
            sql += f""",
    AVG({alias}.progress) as avg_progress,
    MIN({alias}.progress) as min_progress,
    MAX({alias}.progress) as max_progress
"""

        sql += f"\nFROM {table} {alias}\nWHERE 1=1"

        params = {}

        # Apply filters
        sql, params = self._apply_filters(sql, params, query.filters, alias, entity)

        # Apply personalization (if query has "мои/мой/моя")
        if query.personalized and user_id:
            sql, params = self._apply_personalization(sql, params, entity, user_id, alias)

        # Apply RBAC
        sql = self._apply_rbac_filter(sql, entity, user_role, user_id, alias)

        return sql, params

    def generate_comparison_sql(
        self,
        query: AnalyticsQuery,
        user_role: str,
        user_id: Optional[str]
    ) -> Tuple[str, Dict]:
        """Generate SQL for comparison queries"""

        entity = query.entities[0] if query.entities else 'projects'
        schema = self.SCHEMA.get(entity, self.SCHEMA['projects'])

        alias = schema['alias']
        table = schema['table']
        group_col = schema['group_by_column']

        # Use dynamic column name for status
        status_col = self._get_column_name(entity, 'status')

        sql = f"""
SELECT
    {alias}.{group_col} as category,
    COUNT(*) as count,
    AVG(CASE WHEN {alias}.{status_col} = 'completed' THEN 1 ELSE 0 END) * 100 as completion_rate
FROM {table} {alias}
WHERE 1=1
"""

        params = {}

        # Apply filters
        sql, params = self._apply_filters(sql, params, query.filters, alias, entity)

        # Apply personalization (if query has "мои/мой/моя")
        if query.personalized and user_id:
            sql, params = self._apply_personalization(sql, params, entity, user_id, alias)

        # Apply RBAC
        sql = self._apply_rbac_filter(sql, entity, user_role, user_id, alias)

        sql += f"\nGROUP BY {alias}.{group_col}"
        sql += f"\nORDER BY count DESC"
        sql += f"\nLIMIT 20"

        return sql, params

    def generate_ranking_sql(
        self,
        query: AnalyticsQuery,
        user_role: str,
        user_id: Optional[str]
    ) -> Tuple[str, Dict]:
        """
        Generate SQL for TOP N ranking queries with GROUP BY and aggregation.

        Examples:
        - "Топ 3 менеджера по количеству активных проектов"
        - "Какие 5 сотрудников имеют больше всего задач"
        - "Топ проекты по бюджету"
        """
        params = {}

        # Determine what we're ranking and what we're counting
        # Primary entity is what we count/show, related entity is for metrics
        primary_entity = query.entities[0] if query.entities else 'projects'

        # If there's a second entity (like v_budgets_full), use it for JOIN
        related_entity = None
        if len(query.entities) > 1:
            related_entity = query.entities[1]

        # Group entity is what we group by (for employee rankings)
        group_entity = query.group_by_entity or primary_entity

        primary_schema = self.SCHEMA.get(primary_entity, self.SCHEMA['projects'])
        group_schema = self.SCHEMA.get(group_entity, self.SCHEMA['profiles'])

        primary_alias = primary_schema['alias']
        primary_table = primary_schema['table']

        # If grouping by same entity as primary, no separate group table
        if group_entity == primary_entity:
            group_alias = primary_alias
            group_table = primary_table
        else:
            group_alias = group_schema['alias']
            group_table = group_schema['table']

        # Find the join condition
        if group_entity != primary_entity:
            join_condition = self._find_join_condition(
                primary_entity, primary_alias,
                group_entity, group_alias
            )

            if not join_condition:
                # Try reverse direction
                join_condition = self._find_join_condition(
                    group_entity, group_alias,
                    primary_entity, primary_alias
                )

            if not join_condition:
                logger.warning(f"No join condition found between {primary_entity} and {group_entity}")
                return self.generate_report_sql(query, user_role, user_id)
        else:
            # Same entity - no join needed
            join_condition = None

        # Determine metric to order by
        order_metric = query.order_by or 'count'

        # Build SELECT based on group entity (what we show) and metric
        if group_entity == 'profiles':
            select_cols = [
                f"{group_alias}.first_name",
                f"{group_alias}.last_name"
            ]
            group_by_cols = [
                f"{group_alias}.user_id",
                f"{group_alias}.first_name",
                f"{group_alias}.last_name"
            ]
        else:
            name_col = self._get_column_name(group_entity, 'name')
            id_col = self._get_column_name(group_entity, 'id')
            select_cols = [f"{group_alias}.{name_col}"]
            group_by_cols = [f"{group_alias}.{id_col}", f"{group_alias}.{name_col}"]

        # Add the aggregate column
        if order_metric == 'count':
            select_cols.append(f"COUNT({primary_alias}.*) as count")
        elif order_metric in ['total_amount', 'budget']:
            select_cols.append(f"SUM(b.total_amount) as total_budget")
        elif order_metric in ['spent', 'total_spent']:
            # For overrun/overspent queries, calculate (spent - budget) as overrun
            select_cols.append(f"SUM(b.total_spent - b.total_amount) as overrun")
            select_cols.append(f"SUM(b.total_spent) as total_spent")
            select_cols.append(f"SUM(b.total_amount) as total_budget")
        elif order_metric == 'hours':
            select_cols.append(f"SUM(pd.hours_actual_total) as total_hours")
        else:
            select_cols.append(f"COUNT({primary_alias}.*) as count")

        # Build the SQL
        sql = f"""
SELECT
    {', '.join(select_cols)}
FROM {primary_table} {primary_alias}
"""

        # Add JOIN to related entity if exists (e.g., v_budgets_full)
        if related_entity:
            related_schema = self.SCHEMA.get(related_entity)
            if related_schema:
                related_alias = related_schema['alias']
                related_table = related_schema['table']

                # Find join condition to related entity
                related_join = self._find_join_condition(
                    primary_entity, primary_alias,
                    related_entity, related_alias
                )

                if related_join:
                    sql += f"INNER JOIN {related_table} {related_alias} ON {related_join}\n"

        # Add JOIN to group entity if different from primary
        if join_condition:
            sql += f"INNER JOIN {group_table} {group_alias} ON {join_condition}\n"

        sql += "WHERE 1=1\n"

        # Apply filters on primary entity
        status_col = self._get_column_name(primary_entity, 'status')
        if query.filters and query.filters.status:
            sql += f" AND {primary_alias}.{status_col} = %(status)s"
            params['status'] = query.filters.status

        # Apply RBAC
        sql = self._apply_rbac_filter(sql, primary_entity, user_role, user_id, primary_alias)

        # GROUP BY
        sql += f"\nGROUP BY {', '.join(group_by_cols)}"

        # For overrun queries, filter only projects with negative remaining_amount
        if order_metric in ['spent', 'total_spent'] and related_entity == 'v_budgets_full':
            sql += f"\nHAVING SUM(b.total_spent - b.total_amount) > 0"

        # ORDER BY
        order_direction = query.order_direction or 'desc'
        if order_metric == 'count':
            sql += f"\nORDER BY count {order_direction.upper()}"
        elif order_metric in ['total_amount', 'budget']:
            sql += f"\nORDER BY total_budget {order_direction.upper()}"
        elif order_metric in ['spent', 'total_spent']:
            # Order by overrun amount (spent - budget)
            sql += f"\nORDER BY overrun {order_direction.upper()}"
        elif order_metric == 'hours':
            sql += f"\nORDER BY total_hours {order_direction.upper()}"
        else:
            sql += f"\nORDER BY count {order_direction.upper()}"

        # LIMIT
        limit = query.limit or 10
        sql += f"\nLIMIT {limit}"

        return sql, params

    def generate_generic_sql(
        self,
        query: AnalyticsQuery,
        user_role: str,
        user_id: Optional[str]
    ) -> Tuple[str, Dict]:
        """Generate generic SQL for unclassified queries"""

        entity = query.entities[0] if query.entities else 'projects'
        schema = self.SCHEMA.get(entity, self.SCHEMA['projects'])

        alias = schema['alias']
        table = schema['table']

        # Select all main columns
        columns = schema['columns']
        select_cols = [f"{alias}.{col}" for col in columns]

        sql = f"""
SELECT
    {', '.join(select_cols)}
FROM {table} {alias}
WHERE 1=1
"""

        params = {}

        # Apply filters
        sql, params = self._apply_filters(sql, params, query.filters, alias, entity)

        # Apply personalization (if query has "мои/мой/моя")
        if query.personalized and user_id:
            sql, params = self._apply_personalization(sql, params, entity, user_id, alias)

        # Apply RBAC
        sql = self._apply_rbac_filter(sql, entity, user_role, user_id, alias)

        # Use dynamic column name for created_at
        created_col = self._get_column_name(entity, 'created_at')
        sql += f"\nORDER BY {alias}.{created_col} DESC"
        sql += f"\nLIMIT 50"

        return sql, params

    def _apply_filters(
        self,
        sql: str,
        params: Dict,
        filters: FilterOptions,
        alias: str,
        entity: str
    ) -> Tuple[str, Dict]:
        """Apply user-provided filters with parameterization"""

        if not filters:
            return sql, params

        # Use dynamic column names
        status_col = self._get_column_name(entity, 'status')
        created_col = self._get_column_name(entity, 'created_at')

        # Status filter - support multiple statuses separated by comma
        if filters.status:
            # Check if multiple statuses (comma-separated)
            if ',' in filters.status:
                statuses = [s.strip() for s in filters.status.split(',')]
                placeholders = ', '.join([f"%(status_{i})s" for i in range(len(statuses))])
                sql += f" AND {alias}.{status_col} IN ({placeholders})"
                for i, status in enumerate(statuses):
                    params[f'status_{i}'] = status
            else:
                # Single status
                sql += f" AND {alias}.{status_col} = %(status)s"
                params['status'] = filters.status

        # Date range filter
        if filters.date_range:
            if filters.date_range == 'last_week':
                sql += f" AND {alias}.{created_col} >= NOW() - INTERVAL '7 days'"
            elif filters.date_range == 'last_month':
                sql += f" AND {alias}.{created_col} >= NOW() - INTERVAL '30 days'"
            elif filters.date_range == 'last_year':
                sql += f" AND {alias}.{created_col} >= NOW() - INTERVAL '365 days'"

        # Project ID filter (for stages/objects/sections)
        if filters.project_id:
            schema = self.SCHEMA.get(entity)
            if schema and 'project_id' in schema['columns']:
                sql += f" AND {alias}.project_id = %(project_id)s"
                params['project_id'] = filters.project_id

        return sql, params

    def _apply_related_filters(
        self,
        sql: str,
        params: Dict,
        filters: FilterOptions,
        entities: List[str]
    ) -> Tuple[str, Dict]:
        """
        Apply filters on related entities (budget, hours, progress, etc.)

        Args:
            sql: SQL query string
            params: Query parameters
            filters: Filter options with numeric filters
            entities: List of entities in query

        Returns:
            Tuple of (sql, params) with filters applied
        """
        if not filters:
            return sql, params

        # Budget filters (if v_budgets_full is in entities)
        if 'v_budgets_full' in entities:
            if filters.min_budget is not None:
                sql += f" AND b.total_amount >= %(min_budget)s"
                params['min_budget'] = filters.min_budget

            if filters.max_budget is not None:
                sql += f" AND b.total_amount <= %(max_budget)s"
                params['max_budget'] = filters.max_budget

        # Hours filters (if view_project_dashboard is in entities)
        if 'view_project_dashboard' in entities:
            if filters.min_hours is not None:
                sql += f" AND pd.hours_actual_total >= %(min_hours)s"
                params['min_hours'] = filters.min_hours

            if filters.max_hours is not None:
                sql += f" AND pd.hours_actual_total <= %(max_hours)s"
                params['max_hours'] = filters.max_hours

        # Progress filters (on primary entity if it has progress column)
        if filters.min_progress is not None:
            # Try to apply on primary entity (objects, stages, sections have progress)
            primary_entity = entities[0] if entities else None
            if primary_entity in ['objects', 'stages', 'sections', 'decomposition_items']:
                progress_col = self._get_column_name(primary_entity, 'progress')
                alias = self.SCHEMA.get(primary_entity, {}).get('alias', 'p')
                sql += f" AND {alias}.{progress_col} >= %(min_progress)s"
                params['min_progress'] = filters.min_progress

        if filters.max_progress is not None:
            primary_entity = entities[0] if entities else None
            if primary_entity in ['objects', 'stages', 'sections', 'decomposition_items']:
                progress_col = self._get_column_name(primary_entity, 'progress')
                alias = self.SCHEMA.get(primary_entity, {}).get('alias', 'p')
                sql += f" AND {alias}.{progress_col} <= %(max_progress)s"
                params['max_progress'] = filters.max_progress

        return sql, params

    def _apply_personalization(
        self,
        sql: str,
        params: Dict,
        entity: str,
        user_id: str,
        alias: str
    ) -> Tuple[str, Dict]:
        """
        Apply personalization filter when user asks for "my projects/tasks"

        Args:
            sql: SQL query string
            params: Query parameters dict
            entity: Entity name (projects, tasks, etc.)
            user_id: User ID for filtering
            alias: Table alias

        Returns:
            Tuple of (sql, params) with personalization applied
        """
        personalization_filter = None

        if entity == 'projects':
            # Filter by project_manager
            manager_col = self._get_column_name(entity, 'manager')
            personalization_filter = f"{alias}.{manager_col} = %(user_id)s"

        elif entity == 'objects':
            # Filter by object_responsible
            personalization_filter = f"{alias}.object_responsible = %(user_id)s"

        elif entity == 'sections':
            # Filter by section_responsible
            personalization_filter = f"{alias}.section_responsible = %(user_id)s"

        elif entity == 'tasks':
            # Filter by task_responsible
            personalization_filter = f"{alias}.task_responsible = %(user_id)s"

        elif entity == 'stages':
            # Filter stages by objects where user is responsible
            personalization_filter = f"""EXISTS (
                SELECT 1 FROM objects o
                WHERE o.stage_id = {alias}.id
                AND o.responsible_id = %(user_id)s
            )"""

        elif entity == 'decomposition_items':
            # Via section responsible
            personalization_filter = f"""EXISTS (
                SELECT 1 FROM sections s
                WHERE s.section_id = {alias}.decomposition_item_section_id
                AND s.section_responsible = %(user_id)s
            )"""

        # Add filter to SQL
        if personalization_filter:
            sql += f" AND {personalization_filter}"
            params['user_id'] = user_id

        return sql, params

    def _apply_rbac_filter(
        self,
        sql: str,
        entity: str,
        user_role: str,
        user_id: Optional[str],
        alias: str
    ) -> str:
        """Inject RBAC WHERE clause based on user role"""

        rbac_filter = None

        # Use dynamic column name for status
        status_col = self._get_column_name(entity, 'status')

        if user_role == 'guest':
            # Most restrictive - only active/completed, no profiles
            if entity == 'profiles':
                rbac_filter = "1 = 0"  # No access to profiles
            else:
                rbac_filter = f"{alias}.{status_col} IN ('active', 'completed')"

        elif user_role == 'viewer':
            # Can see all except cancelled
            rbac_filter = f"{alias}.{status_col} != 'cancelled'"

        elif user_role == 'engineer' and user_id:
            # Personalized - only user's assigned objects
            if entity == 'objects':
                rbac_filter = f"{alias}.object_responsible = %(user_id)s"
            elif entity == 'stages':
                # Via JOIN: only stages with user's objects
                rbac_filter = f"""EXISTS (
                    SELECT 1 FROM objects o
                    WHERE o.object_stage_id = {alias}.stage_id
                    AND o.object_responsible = %(user_id)s
                )"""
            elif entity == 'projects':
                # Via nested JOIN: only projects with user's objects
                rbac_filter = f"""EXISTS (
                    SELECT 1 FROM stages s
                    INNER JOIN objects o ON o.object_stage_id = s.stage_id
                    WHERE s.stage_project_id = {alias}.project_id
                    AND o.object_responsible = %(user_id)s
                )"""

        elif user_role in ['manager', 'admin']:
            # Full access - no additional filter
            pass

        # Inject filter into SQL
        if rbac_filter:
            if 'WHERE' in sql.upper():
                sql += f" AND {rbac_filter}"
            else:
                sql += f" WHERE {rbac_filter}"

        return sql

    def _inject_parameters_safe(self, sql: str, params: Dict) -> str:
        """
        Inject parameters into SQL with SQL injection protection

        Replaces %(param_name)s placeholders with escaped values
        """
        for key, value in params.items():
            placeholder = f"%({key})s"

            if isinstance(value, str):
                # Escape single quotes (SQL standard: ' becomes '')
                escaped = value.replace("'", "''")
                sql = sql.replace(placeholder, f"'{escaped}'")

            elif isinstance(value, (int, float)):
                sql = sql.replace(placeholder, str(value))

            elif value is None:
                sql = sql.replace(placeholder, "NULL")

            elif isinstance(value, bool):
                sql = sql.replace(placeholder, 'TRUE' if value else 'FALSE')

        return sql

    def _build_auto_joins(
        self,
        entity: str,
        required_relations: List[str]
    ) -> str:
        """
        Build JOIN clauses based on SCHEMA relations

        Args:
            entity: Main entity name
            required_relations: List of relation names to join

        Returns:
            SQL JOIN clauses
        """
        schema = self.SCHEMA.get(entity)
        if not schema:
            return ""

        joins = []
        for rel_name, (rel_table, fk, pk) in schema.get('relations', {}).items():
            if rel_name in required_relations:
                rel_schema = self.SCHEMA.get(rel_table)
                if rel_schema:
                    rel_alias = rel_schema['alias']
                    joins.append(
                        f"LEFT JOIN {rel_table} {rel_alias} "
                        f"ON {rel_alias}.{pk} = {schema['alias']}.{fk}"
                    )

        return "\n".join(joins)
