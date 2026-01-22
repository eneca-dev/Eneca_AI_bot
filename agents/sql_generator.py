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

        # Build SELECT clause with columns from all entities
        select_columns = []

        # Add primary entity columns
        for col in primary_schema['columns']:
            if not (col.endswith('_id') or col == 'id'):  # Skip IDs
                select_columns.append(f"{primary_alias}.{col}")

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
                joins.append(f"LEFT JOIN {related_table} {related_alias} ON {join_condition}")

                # Add related entity columns (exclude IDs)
                for col in related_schema['columns']:
                    if not (col.endswith('_id') or col == 'id'):
                        # Add prefix to avoid column name conflicts
                        select_columns.append(f"{related_alias}.{col} as {related_entity}_{col}")

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

        # Apply filters
        sql, params = self._apply_filters(sql, params, query.filters, primary_alias, primary_entity)

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
        """Generate SQL for chart visualization (pie, bar, line)"""

        entity = query.entities[0] if query.entities else 'projects'
        schema = self.SCHEMA.get(entity, self.SCHEMA['projects'])

        alias = schema['alias']
        table = schema['table']
        group_col = schema['group_by_column']

        sql = f"""
SELECT
    {alias}.{group_col} as label,
    COUNT(*) as value
FROM {table} {alias}
WHERE 1=1
"""

        params = {}

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

        # Select main columns
        select_cols = [f"{alias}.{col}" for col in columns[:7]]  # First 7 columns

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

        # Status filter
        if filters.status:
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
