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
                'stages': ('stages', 'stage_project_id', 'project_id'),
                'manager': ('profiles', 'id', 'project_manager')
            },
            'group_by_column': 'project_status',
            'label_column': 'project_name',
            'value_column': 'project_id'
        },
        'stages': {
            'table': 'stages',
            'alias': 's',
            'columns': [
                'id', 'project_id', 'name', 'description',
                'start_date', 'end_date', 'progress', 'status'
            ],
            'relations': {
                'project': ('projects', 'id', 'project_id'),
                'objects': ('objects', 'stage_id', 'id')
            },
            'group_by_column': 'status',
            'label_column': 'name',
            'value_column': 'progress'
        },
        'objects': {
            'table': 'objects',
            'alias': 'o',
            'columns': [
                'id', 'stage_id', 'name', 'description',
                'responsible_id', 'status', 'progress'
            ],
            'relations': {
                'stage': ('stages', 'id', 'stage_id'),
                'responsible': ('profiles', 'id', 'responsible_id'),
                'sections': ('sections', 'object_id', 'id')
            },
            'group_by_column': 'status',
            'label_column': 'name',
            'value_column': 'progress'
        },
        'sections': {
            'table': 'sections',
            'alias': 'sec',
            'columns': [
                'id', 'object_id', 'name', 'description',
                'progress', 'status'
            ],
            'relations': {
                'object': ('objects', 'id', 'object_id')
            },
            'group_by_column': 'status',
            'label_column': 'name',
            'value_column': 'progress'
        },
        'profiles': {
            'table': 'profiles',
            'alias': 'u',
            'columns': [
                'id', 'email', 'first_name', 'last_name',
                'job_title', 'department', 'phone', 'created_at'
            ],
            'relations': {
                'assigned_objects': ('objects', 'responsible_id', 'id')
            },
            'group_by_column': 'department',
            'label_column': 'first_name',
            'value_column': 'id'
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

        if parsed_query.intent == "chart":
            return self.generate_chart_sql(parsed_query, user_role, user_id)
        elif parsed_query.intent == "report":
            return self.generate_report_sql(parsed_query, user_role, user_id)
        elif parsed_query.intent == "statistics":
            return self.generate_statistics_sql(parsed_query, user_role, user_id)
        elif parsed_query.intent == "comparison":
            return self.generate_comparison_sql(parsed_query, user_role, user_id)
        else:
            return self.generate_generic_sql(parsed_query, user_role, user_id)

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
                rbac_filter = f"{alias}.responsible_id = %(user_id)s"
            elif entity == 'stages':
                # Via JOIN: only stages with user's objects
                rbac_filter = f"""EXISTS (
                    SELECT 1 FROM objects o
                    WHERE o.stage_id = {alias}.id
                    AND o.responsible_id = %(user_id)s
                )"""
            elif entity == 'projects':
                # Via nested JOIN: only projects with user's objects
                rbac_filter = f"""EXISTS (
                    SELECT 1 FROM stages s
                    INNER JOIN objects o ON o.stage_id = s.id
                    WHERE s.project_id = {alias}.id
                    AND o.responsible_id = %(user_id)s
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
