"""Basic tests for Analytics Agent"""
import pytest
from agents.analytics_agent import AnalyticsAgent, AnalyticsQuery, AnalyticsResult


class TestAnalyticsAgent:
    """Test suite for AnalyticsAgent"""

    @pytest.fixture
    def agent(self):
        """Create Analytics Agent instance"""
        return AnalyticsAgent()

    def test_agent_initialization(self, agent):
        """Test that agent initializes correctly"""
        assert agent is not None
        assert agent.llm is not None
        assert agent.query_llm is not None

    def test_parse_statistics_query(self, agent):
        """Test parsing statistics query"""
        result = agent._parse_user_query("Сколько проектов в системе?")

        assert isinstance(result, AnalyticsQuery)
        assert result.intent in ["statistics", "report", "chart"]
        assert "projects" in result.entities or len(result.entities) == 0

    def test_parse_chart_query(self, agent):
        """Test parsing chart query"""
        result = agent._parse_user_query("Покажи график проектов по статусам")

        assert isinstance(result, AnalyticsQuery)
        assert result.intent in ["chart", "report"]
        assert result.chart_type in ["pie", "bar", "line", None]

    def test_generate_report_sql(self, agent):
        """Test SQL generation for reports"""
        query = AnalyticsQuery(
            intent="report",
            entities=["projects"],
            metrics=["count", "progress"]
        )

        sql = agent._generate_sql(query)

        assert "SELECT" in sql.upper()
        assert "projects" in sql.lower()

    def test_generate_chart_sql(self, agent):
        """Test SQL generation for charts"""
        query = AnalyticsQuery(
            intent="chart",
            entities=["projects"],
            metrics=["count"],
            chart_type="pie"
        )

        sql = agent._generate_sql(query)

        assert "SELECT" in sql.upper()
        assert "GROUP BY" in sql.upper() or "COUNT" in sql.upper()

    def test_execute_sql_returns_list(self, agent):
        """Test that SQL execution returns list of dicts"""
        sql = "SELECT * FROM projects LIMIT 5"
        result = agent._execute_sql(sql)

        assert isinstance(result, list)
        if len(result) > 0:
            assert isinstance(result[0], dict)

    def test_prepare_pie_chart(self, agent):
        """Test pie chart configuration generation"""
        data = [
            {"label": "active", "value": 10},
            {"label": "completed", "value": 5}
        ]

        config = agent._prepare_chart_data(data, "pie")

        assert config["type"] == "pie"
        assert "data" in config
        assert "labels" in config["data"]
        assert "datasets" in config["data"]
        assert len(config["data"]["labels"]) == 2

    def test_prepare_bar_chart(self, agent):
        """Test bar chart configuration generation"""
        data = [
            {"label": "Project A", "value": 75},
            {"label": "Project B", "value": 50}
        ]

        config = agent._prepare_chart_data(data, "bar")

        assert config["type"] == "bar"
        assert "scales" in config["options"]

    def test_process_analytics_returns_result(self, agent):
        """Test full analytics processing pipeline"""
        result = agent.process_analytics(
            user_query="Статистика проектов",
            user_role="admin"
        )

        assert isinstance(result, AnalyticsResult)
        assert result.type in ["text", "table", "chart", "mixed"]
        assert result.content is not None

    def test_process_analytics_with_rbac(self, agent):
        """Test analytics with different roles"""
        # Admin should get full data
        admin_result = agent.process_analytics(
            user_query="Покажи проекты",
            user_role="admin"
        )
        assert admin_result.success or admin_result.type == "text"

        # Guest should get limited data
        guest_result = agent.process_analytics(
            user_query="Покажи проекты",
            user_role="guest"
        )
        assert guest_result.success or guest_result.type == "text"

    def test_answer_question_returns_json(self, agent):
        """Test that answer_question returns JSON string"""
        result = agent.answer_question("Статистика проектов", user_role="admin")

        assert isinstance(result, str)
        # Should be valid JSON
        import json
        parsed = json.loads(result)
        assert "type" in parsed
        assert "content" in parsed


class TestAnalyticsQuery:
    """Test AnalyticsQuery Pydantic model"""

    def test_create_query_with_defaults(self):
        """Test creating query with default values"""
        query = AnalyticsQuery(
            intent="report",
            entities=["projects"]
        )

        assert query.intent == "report"
        assert query.entities == ["projects"]
        assert query.metrics == []
        assert query.filters == {}
        assert query.aggregation is None
        assert query.chart_type is None

    def test_create_full_query(self):
        """Test creating query with all fields"""
        query = AnalyticsQuery(
            intent="chart",
            entities=["projects", "stages"],
            metrics=["count", "avg_progress"],
            filters={"status": "active"},
            aggregation="by_project",
            chart_type="bar"
        )

        assert query.intent == "chart"
        assert len(query.entities) == 2
        assert len(query.metrics) == 2
        assert query.filters["status"] == "active"
        assert query.chart_type == "bar"


class TestAnalyticsResult:
    """Test AnalyticsResult Pydantic model"""

    def test_create_text_result(self):
        """Test creating text result"""
        result = AnalyticsResult(
            type="text",
            content="Статистика: 10 проектов"
        )

        assert result.type == "text"
        assert isinstance(result.content, str)
        assert result.success

    def test_create_table_result(self):
        """Test creating table result"""
        result = AnalyticsResult(
            type="table",
            content=[
                {"id": 1, "name": "Project 1"},
                {"id": 2, "name": "Project 2"}
            ],
            sql_query="SELECT id, name FROM projects"
        )

        assert result.type == "table"
        assert isinstance(result.content, list)
        assert len(result.content) == 2
        assert result.sql_query is not None

    def test_create_chart_result(self):
        """Test creating chart result"""
        result = AnalyticsResult(
            type="chart",
            content=[{"label": "active", "value": 10}],
            chart_config={
                "type": "pie",
                "data": {"labels": ["active"], "datasets": [{"data": [10]}]}
            }
        )

        assert result.type == "chart"
        assert result.chart_config is not None
        assert result.chart_config["type"] == "pie"


# Integration test (requires running server)
class TestAnalyticsEndpoint:
    """Integration tests for /api/analytics endpoint"""

    @pytest.mark.skip(reason="Requires running server")
    def test_analytics_endpoint_basic(self):
        """Test basic analytics endpoint call"""
        import requests

        response = requests.post(
            "http://localhost:8000/api/analytics",
            json={
                "query": "Статистика проектов",
                "user_role": "admin"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "type" in data
        assert "content" in data

    @pytest.mark.skip(reason="Requires running server")
    def test_analytics_endpoint_with_auth(self):
        """Test analytics endpoint with API key"""
        import requests
        import os

        api_key = os.getenv("API_KEY", "test_key")

        response = requests.post(
            "http://localhost:8000/api/analytics",
            json={
                "query": "Покажи проекты по статусам",
                "user_role": "manager"
            },
            headers={"X-API-Key": api_key}
        )

        assert response.status_code in [200, 401]  # 401 if key is wrong

    @pytest.mark.skip(reason="Requires running server")
    def test_analytics_endpoint_chart_response(self):
        """Test that chart query returns chart config"""
        import requests

        response = requests.post(
            "http://localhost:8000/api/analytics",
            json={
                "query": "Покажи график проектов по статусам",
                "user_role": "admin"
            }
        )

        assert response.status_code == 200
        data = response.json()

        if data["type"] == "chart":
            assert "chart_config" in data
            assert data["chart_config"] is not None
            assert "type" in data["chart_config"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
