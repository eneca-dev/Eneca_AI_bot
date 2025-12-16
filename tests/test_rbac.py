"""
Unit tests for RBAC (Role-Based Access Control) system
Tests permission checking, role hierarchy, and access control logic
"""
import pytest
from core.rbac import rbac_manager


class TestRBACManager:
    """Test suite for RBACManager"""

    def test_admin_full_access(self):
        """Test that admin role has access to all dangerous operations"""
        # Admin should have wildcard (*) access
        allowed, error = rbac_manager.check_permission("admin", "create_project")
        assert allowed == True
        assert error is None

        allowed, error = rbac_manager.check_permission("admin", "update_project")
        assert allowed == True
        assert error is None

        allowed, error = rbac_manager.check_permission("admin", "create_stage")
        assert allowed == True
        assert error is None

    def test_manager_permissions(self):
        """Test that manager role has correct dangerous operation permissions"""
        # Manager should be able to create/update projects
        allowed, error = rbac_manager.check_permission("manager", "create_project")
        assert allowed == True
        assert error is None

        allowed, error = rbac_manager.check_permission("manager", "update_project")
        assert allowed == True
        assert error is None

        # Manager should be able to create/update stages
        allowed, error = rbac_manager.check_permission("manager", "create_stage")
        assert allowed == True
        assert error is None

    def test_engineer_permissions(self):
        """Test that engineer role has limited dangerous operation permissions"""
        # Engineer should be able to create/update objects and sections
        allowed, error = rbac_manager.check_permission("engineer", "create_object")
        assert allowed == True
        assert error is None

        allowed, error = rbac_manager.check_permission("engineer", "update_section")
        assert allowed == True
        assert error is None

        # Engineer should NOT be able to create/update projects
        allowed, error = rbac_manager.check_permission("engineer", "create_project")
        assert allowed == False
        assert "нет прав" in error.lower()
        assert "engineer" in error

    def test_viewer_blocked_all_dangerous(self):
        """Test that viewer role is blocked from all dangerous operations"""
        allowed, error = rbac_manager.check_permission("viewer", "create_project")
        assert allowed == False
        assert "нет прав" in error.lower()

        allowed, error = rbac_manager.check_permission("viewer", "update_stage")
        assert allowed == False
        assert "нет прав" in error.lower()

    def test_guest_blocked_all_dangerous(self):
        """Test that guest role is blocked from all dangerous operations"""
        allowed, error = rbac_manager.check_permission("guest", "create_project")
        assert allowed == False
        assert "нет прав" in error.lower()
        assert "guest" in error

        allowed, error = rbac_manager.check_permission("guest", "update_object")
        assert allowed == False
        assert "нет прав" in error.lower()

    def test_safe_operations_allowed_for_all(self):
        """Test that safe (read-only) operations are allowed for all roles"""
        # Safe operations should pass hard check for all roles
        for role in ["admin", "manager", "engineer", "viewer", "guest"]:
            allowed, error = rbac_manager.check_permission(role, "search_projects")
            assert allowed == True, f"search_projects should be allowed for {role}"
            assert error is None

            allowed, error = rbac_manager.check_permission(role, "search_employee_full_info")
            assert allowed == True, f"search_employee_full_info should be allowed for {role}"
            assert error is None

    def test_unknown_role_defaults_to_guest(self):
        """Test that unknown roles default to guest permissions"""
        allowed, error = rbac_manager.check_permission("unknown_role", "create_project")
        assert allowed == False
        assert "нет прав" in error.lower()

    def test_none_role_defaults_to_guest(self):
        """Test that None role defaults to guest permissions"""
        allowed, error = rbac_manager.check_permission(None, "create_project")
        assert allowed == False
        assert "нет прав" in error.lower()
        assert "guest" in error

    def test_permission_error_message_format(self):
        """Test that permission denied error messages are properly formatted in Russian"""
        allowed, error = rbac_manager.check_permission("guest", "create_project")
        assert allowed == False
        assert error is not None
        assert "У вас нет прав для этой операции" in error
        assert "guest" in error
        assert "create_project" in error

    def test_is_tool_dangerous(self):
        """Test tool categorization into dangerous vs safe"""
        # Dangerous tools
        assert rbac_manager.is_tool_dangerous("create_project") == True
        assert rbac_manager.is_tool_dangerous("update_stage") == True
        assert rbac_manager.is_tool_dangerous("create_object") == True

        # Safe tools
        assert rbac_manager.is_tool_dangerous("search_projects") == False
        assert rbac_manager.is_tool_dangerous("get_project_details") == False
        assert rbac_manager.is_tool_dangerous("search_employee_full_info") == False

    def test_get_soft_restrictions(self):
        """Test retrieval of soft restrictions for LLM prompt injection"""
        # Admin should have no soft restrictions
        admin_restrictions = rbac_manager.get_soft_restrictions("admin")
        assert admin_restrictions is None

        # Guest should have soft restrictions
        guest_restrictions = rbac_manager.get_soft_restrictions("guest")
        assert guest_restrictions is not None
        assert "guest" in guest_restrictions.lower() or "гость" in guest_restrictions.lower()

        # Viewer should have soft restrictions
        viewer_restrictions = rbac_manager.get_soft_restrictions("viewer")
        assert viewer_restrictions is not None
        assert "viewer" in viewer_restrictions.lower() or "наблюдатель" in viewer_restrictions.lower()

    def test_get_role_level(self):
        """Test role hierarchy numeric levels"""
        assert rbac_manager.get_role_level("admin") == 100
        assert rbac_manager.get_role_level("manager") == 50
        assert rbac_manager.get_role_level("engineer") == 30
        assert rbac_manager.get_role_level("viewer") == 10
        assert rbac_manager.get_role_level("guest") == 0
        assert rbac_manager.get_role_level("unknown") == 0  # Default

    def test_get_allowed_dangerous_tools(self):
        """Test retrieval of allowed dangerous tools per role"""
        # Admin should have wildcard
        admin_tools = rbac_manager.get_allowed_dangerous_tools("admin")
        assert admin_tools == ["*"]

        # Manager should have explicit list
        manager_tools = rbac_manager.get_allowed_dangerous_tools("manager")
        assert "create_project" in manager_tools
        assert "update_stage" in manager_tools

        # Guest should have empty list
        guest_tools = rbac_manager.get_allowed_dangerous_tools("guest")
        assert guest_tools == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
