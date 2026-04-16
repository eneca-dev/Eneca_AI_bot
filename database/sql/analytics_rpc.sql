-- Analytics RPC Function for Safe SQL Execution
-- Provides secure SQL execution for Analytics Agent with injection protection

-- Drop existing function if any
DROP FUNCTION IF EXISTS execute_analytics_query(TEXT, TEXT);

-- Create the RPC function
CREATE OR REPLACE FUNCTION execute_analytics_query(
    query_text TEXT,
    user_role_name TEXT DEFAULT 'guest'
)
RETURNS TABLE(result JSONB)
SECURITY DEFINER
SET search_path = public
LANGUAGE plpgsql
AS $$
DECLARE
    query_upper TEXT;
    forbidden_keywords TEXT[] := ARRAY[
        'INSERT', 'UPDATE', 'DELETE', 'DROP', 'TRUNCATE',
        'ALTER', 'CREATE', 'GRANT', 'REVOKE', 'EXECUTE'
    ];
    keyword TEXT;
BEGIN
    -- Remove SQL comments to prevent bypass attempts
    query_upper := UPPER(REGEXP_REPLACE(query_text, '--.*', '', 'g'));
    query_upper := UPPER(REGEXP_REPLACE(query_upper, '/\*.*?\*/', '', 'g'));

    -- Validate that query starts with SELECT
    IF query_upper !~ '^\s*SELECT' THEN
        RAISE EXCEPTION 'Only SELECT queries are allowed';
    END IF;

    -- Block dangerous keywords (write operations, DDL, etc.)
    FOREACH keyword IN ARRAY forbidden_keywords LOOP
        IF query_upper ~ ('\m' || keyword || '\M') THEN
            RAISE EXCEPTION 'Forbidden keyword detected: %', keyword;
        END IF;
    END LOOP;

    -- Set timeout protection (30 seconds max)
    SET LOCAL statement_timeout = '30s';

    -- Execute query and return results as JSONB
    -- Each row is converted to JSON object
    RETURN QUERY EXECUTE format(
        'SELECT row_to_json(t)::jsonb FROM (%s) t',
        query_text
    );

EXCEPTION
    WHEN OTHERS THEN
        -- Log error and re-raise with context
        RAISE EXCEPTION 'Query execution failed: %', SQLERRM;
END;
$$;

-- Grant execute permission to service_role (used by Analytics Agent)
GRANT EXECUTE ON FUNCTION execute_analytics_query TO service_role;

-- Grant execute permission to authenticated users (optional, for testing)
GRANT EXECUTE ON FUNCTION execute_analytics_query TO authenticated;

-- Add comment for documentation
COMMENT ON FUNCTION execute_analytics_query IS
'Executes SELECT-only SQL queries safely for analytics purposes.
Blocks write operations, DDL, and enforces 30s timeout.
Returns results as JSONB for flexible parsing.
Used by Analytics Agent for dashboard queries.';
