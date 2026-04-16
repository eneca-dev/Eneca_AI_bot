# Supabase SQL Setup for Analytics Agent

This directory contains SQL scripts for setting up the Analytics Agent's RPC function in Supabase.

## Files

- `analytics_rpc.sql` - RPC function for safe SQL execution with injection protection

## Setup Instructions

### 1. Access Supabase SQL Editor

1. Go to your Supabase project dashboard: https://supabase.com/dashboard
2. Navigate to: **SQL Editor** (left sidebar)

### 2. Execute the RPC Function

1. Open `analytics_rpc.sql` in a text editor
2. Copy the entire contents
3. Paste into the Supabase SQL Editor
4. Click **Run** (or press Ctrl+Enter)

Expected output: `Success. No rows returned`

### 3. Verify Installation

Run this test query in the SQL Editor:

```sql
SELECT execute_analytics_query(
    'SELECT COUNT(*) as count FROM projects',
    'admin'
);
```

Expected output:
```json
[
  {
    "result": {"count": 5}
  }
]
```

### 4. Troubleshooting

**Error: "relation 'projects' does not exist"**
- Make sure your `projects` table is created in the `public` schema
- Check that you're running the query in the correct Supabase project (RAG vs CHAT)

**Error: "permission denied for function execute_analytics_query"**
- Re-run the GRANT statements from `analytics_rpc.sql`:
  ```sql
  GRANT EXECUTE ON FUNCTION execute_analytics_query TO service_role;
  GRANT EXECUTE ON FUNCTION execute_analytics_query TO authenticated;
  ```

**Error: "forbidden keyword detected"**
- The RPC function blocks INSERT/UPDATE/DELETE/DROP operations by design
- Only SELECT queries are allowed
- Check your SQL for forbidden keywords

## Security Features

The RPC function includes multiple layers of protection:

1. **SELECT-only validation** - Only allows queries starting with SELECT
2. **Keyword blocking** - Blocks INSERT, UPDATE, DELETE, DROP, TRUNCATE, ALTER, CREATE, GRANT, REVOKE
3. **Comment stripping** - Removes SQL comments to prevent bypass attempts
4. **Timeout protection** - 30 second query timeout
5. **SECURITY DEFINER** - Executes with owner privileges (controlled access)
6. **Schema isolation** - `SET search_path = public` prevents schema injection

## Usage in Analytics Agent

The Analytics Agent automatically uses this RPC function to execute SQL queries:

```python
from agents.analytics_agent import AnalyticsAgent

agent = AnalyticsAgent()
result = agent.process_analytics(
    user_query="Show project statistics",
    user_role="admin",
    user_id="user-uuid-here"
)
```

The agent will:
1. Parse the natural language query
2. Generate safe SQL with RBAC filtering
3. Execute via `execute_analytics_query` RPC function
4. Return results in frontend-friendly format (table/chart)

## Testing

After setup, test the Analytics Agent endpoints:

### Test 1: Basic Query
```bash
curl -X POST http://localhost:8000/api/analytics \
  -H "Content-Type: application/json" \
  -d '{"query": "Show all projects", "user_role": "admin"}'
```

### Test 2: RBAC Filtering (Guest Role)
```bash
curl -X POST http://localhost:8000/api/analytics \
  -H "Content-Type: application/json" \
  -d '{"query": "Show all projects", "user_role": "guest"}'
```

Guest users should only see active/completed projects and no sensitive data.

### Test 3: Personalized Query (Engineer)
```bash
curl -X POST http://localhost:8000/api/analytics \
  -H "Content-Type: application/json" \
  -d '{"query": "Show my tasks", "user_id": "real-uuid", "user_role": "engineer"}'
```

Engineer should only see their assigned objects.

## Monitoring

Check logs for SQL execution:
```bash
# In app.py or analytics_agent.py logs
grep "Executing SQL" logs/app.log
grep "Circuit breaker" logs/app.log
```

Circuit breaker will open after 5 consecutive failures and attempt recovery after 60 seconds.

## Maintenance

### Update the RPC Function

If you need to modify the RPC function:

1. Edit `analytics_rpc.sql`
2. Run the updated SQL in Supabase SQL Editor
3. The `CREATE OR REPLACE FUNCTION` will update the existing function
4. No need to restart the Analytics Agent

### Check Function Definition

View the current function in Supabase:

```sql
SELECT prosrc FROM pg_proc WHERE proname = 'execute_analytics_query';
```

### Delete Function (if needed)

```sql
DROP FUNCTION IF EXISTS execute_analytics_query(TEXT, TEXT);
```

## Related Files

- `d:\Eneca_AI_bot\agents\analytics_agent.py` - Main Analytics Agent implementation
- `d:\Eneca_AI_bot\agents\sql_generator.py` - SQL generation with RBAC
- `d:\Eneca_AI_bot\prompts\analytics_agent.md` - System prompt with SQL examples
- `d:\Eneca_AI_bot\app.py` - FastAPI endpoint (line 167-234)
