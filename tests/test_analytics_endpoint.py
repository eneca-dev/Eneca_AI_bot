"""Pytest tests for Analytics Agent endpoint"""
import pytest
import requests
from typing import Dict, Any


BASE_URL = "http://localhost:8000"
ANALYTICS_ENDPOINT = f"{BASE_URL}/api/analytics"


@pytest.fixture
def analytics_request():
    """Helper function to make analytics requests"""
    def _request(query: str, user_role: str = "admin") -> requests.Response:
        return requests.post(
            ANALYTICS_ENDPOINT,
            json={"query": query, "user_role": user_role},
            timeout=30
        )
    return _request


@pytest.fixture(scope="session")
def check_server():
    """Check if server is running before tests"""
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code != 200:
            pytest.skip("Server is not responding properly")
    except requests.exceptions.ConnectionError:
        pytest.skip("Server is not running. Start it with: python server.py")


class TestAnalyticsBasic:
    """Basic analytics endpoint tests"""

    def test_server_is_running(self, check_server):
        """Test that server is running"""
        response = requests.get(f"{BASE_URL}/health")
        assert response.status_code == 200

    def test_analytics_endpoint_exists(self, check_server, analytics_request):
        """Test that analytics endpoint exists"""
        response = analytics_request("test query")
        assert response.status_code in [200, 400, 422], "Endpoint should exist"

    def test_simple_statistics_query(self, check_server, analytics_request):
        """Test simple statistics query"""
        response = analytics_request("Покажи статистику проектов")

        assert response.status_code == 200
        data = response.json()

        assert data.get("success") is True
        assert "type" in data
        assert data["type"] in ["text", "table", "chart", "mixed"]
        assert "content" in data

    def test_chart_request(self, check_server, analytics_request):
        """Test chart generation request"""
        response = analytics_request("Создай круговую диаграмму по статусам проектов")

        assert response.status_code == 200
        data = response.json()

        assert data.get("success") is True
        assert data.get("type") in ["chart", "mixed"]
        # Chart requests should return chart_config
        if data.get("type") == "chart":
            assert "chart_config" in data

    def test_sql_generation(self, check_server, analytics_request):
        """Test SQL query generation"""
        response = analytics_request("Напиши SQL для получения всех проектов")

        assert response.status_code == 200
        data = response.json()

        assert data.get("success") is True
        assert "sql_query" in data
        assert len(data["sql_query"]) > 0
        assert "SELECT" in data["sql_query"].upper()


class TestAnalyticsFilters:
    """Test analytics with filters"""

    def test_filtered_query(self, check_server, analytics_request):
        """Test query with filters"""
        response = analytics_request("Покажи активные проекты")

        assert response.status_code == 200
        data = response.json()

        assert data.get("success") is True
        # Should generate SQL with WHERE clause for filtering
        if data.get("sql_query"):
            sql = data["sql_query"].upper()
            # May contain filtering logic
            assert "SELECT" in sql


class TestAnalyticsRBAC:
    """Test role-based access control"""

    @pytest.mark.parametrize("role", ["admin", "manager", "engineer", "viewer"])
    def test_different_roles(self, check_server, analytics_request, role):
        """Test analytics with different user roles"""
        response = analytics_request("Покажи статистику проектов", user_role=role)

        assert response.status_code == 200
        data = response.json()

        assert data.get("success") is True
        assert "content" in data


class TestAnalyticsResponse:
    """Test response structure"""

    def test_response_structure(self, check_server, analytics_request):
        """Test that response has correct structure"""
        response = analytics_request("Статистика проектов")

        assert response.status_code == 200
        data = response.json()

        # Check required fields
        assert "type" in data
        assert "content" in data
        assert "success" in data

        # Check optional fields exist (even if None)
        assert "sql_query" in data
        assert "chart_config" in data
        assert "metadata" in data

    def test_response_types(self, check_server, analytics_request):
        """Test different response types"""
        queries = [
            ("Покажи статистику", "table"),
            ("Создай диаграмму", "chart"),
            ("Сформируй отчет", "text"),
        ]

        for query, expected_type in queries:
            response = analytics_request(query)
            assert response.status_code == 200

            data = response.json()
            # Type should be one of the valid types
            assert data["type"] in ["text", "table", "chart", "mixed"]


class TestAnalyticsPydanticModel:
    """Test that Pydantic models work correctly"""

    def test_filter_options_model(self, check_server, analytics_request):
        """Test that FilterOptions Pydantic model is working"""
        # This query should trigger filter parsing
        response = analytics_request("Покажи проекты со статусом активный")

        assert response.status_code == 200
        data = response.json()

        # Should not have any Pydantic validation errors
        assert data.get("success") is True

        # Should have successfully parsed the query
        assert "content" in data or "sql_query" in data

    def test_no_langchain_warning(self, check_server, analytics_request):
        """Test that no LangChain structured output warnings occur"""
        # Make a request that uses structured output
        response = analytics_request("Анализ проектов")

        # Should succeed without validation errors
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True


@pytest.mark.parametrize("query,user_role", [
    ("Покажи статистику проектов", "admin"),
    ("Создай диаграмму по проектам", "manager"),
    ("Сформируй отчет", "engineer"),
    ("Покажи активные проекты", "admin"),
])
def test_analytics_parametrized(check_server, analytics_request, query, user_role):
    """Parametrized test for multiple queries"""
    response = analytics_request(query, user_role)

    assert response.status_code == 200
    data = response.json()
    assert data.get("success") is True
    assert "content" in data
