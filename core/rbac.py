"""
RBAC (Role-Based Access Control) Manager
Handles permission checking for MCP tools based on user roles
"""
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
import yaml
from loguru import logger


class RBACManager:
    """
    Singleton manager for RBAC permissions

    Loads permission configuration from config/permissions.yaml and provides:
    - Hard permission checks for dangerous operations (create, update, delete)
    - Soft restrictions for LLM injection (read operations)
    - Role hierarchy for future access level comparisons
    """

    def __init__(self):
        """Initialize RBAC manager and load permissions from YAML"""
        self.permissions: Dict[str, Any] = {}
        self.tool_categories: Dict[str, List[str]] = {}
        self.role_hierarchy: Dict[str, int] = {}
        self._load_permissions()

    def _load_permissions(self):
        """Load permissions from YAML configuration file"""
        config_path = Path(__file__).parent.parent / "config" / "permissions.yaml"

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            # Load role hierarchy
            self.role_hierarchy = config.get("role_hierarchy", {})

            # Load tool categories (dangerous vs safe)
            categories = config.get("tool_categories", {})
            self.tool_categories = {
                "dangerous": categories.get("dangerous", {}).get("tools", []),
                "safe": categories.get("safe", {}).get("tools", [])
            }

            # Load per-role permissions
            self.permissions = config.get("permissions", {})

            logger.info(
                f"RBAC permissions loaded successfully: "
                f"{len(self.permissions)} roles, "
                f"{len(self.tool_categories['dangerous'])} dangerous tools, "
                f"{len(self.tool_categories['safe'])} safe tools"
            )
            logger.debug(f"Available roles: {list(self.permissions.keys())}")

        except FileNotFoundError:
            logger.error(f"Permissions config not found at {config_path}")
            logger.warning("RBAC system disabled - all users will have guest role with no dangerous operations")
            # Fallback to minimal guest permissions
            self.permissions = {
                "guest": {
                    "description": "Minimal permissions (fallback)",
                    "allowed_dangerous_tools": []
                }
            }
        except yaml.YAMLError as e:
            logger.error(f"Invalid YAML in permissions config: {e}")
            self.permissions = {"guest": {"allowed_dangerous_tools": []}}
        except Exception as e:
            logger.error(f"Error loading permissions: {e}")
            self.permissions = {"guest": {"allowed_dangerous_tools": []}}

    def is_tool_dangerous(self, tool_name: str) -> bool:
        """
        Check if a tool is categorized as dangerous (modifies data)

        Args:
            tool_name: Name of the MCP tool

        Returns:
            True if tool is dangerous, False if safe
        """
        return tool_name in self.tool_categories.get("dangerous", [])

    def check_permission(
        self,
        role_name: str,
        tool_name: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if a role has permission to use a tool (hard permission check)

        This method performs HARD CHECKS for dangerous operations only.
        Safe operations (read-only) always pass this check and are controlled
        via soft restrictions in the LLM system prompt.

        Args:
            role_name: User's role name (e.g., "admin", "manager", "guest")
            tool_name: Name of the MCP tool to check

        Returns:
            Tuple of (allowed: bool, error_message: Optional[str])
            - (True, None) if permission granted
            - (False, "error message in Russian") if permission denied
        """
        # Normalize role name (default to guest if None)
        role_name = role_name or "guest"

        # Get role permissions
        role_perms = self.permissions.get(role_name)
        if not role_perms:
            logger.warning(f"Unknown role '{role_name}', defaulting to guest permissions")
            role_perms = self.permissions.get("guest", {})

        # Check if tool is dangerous (needs hard check)
        if not self.is_tool_dangerous(tool_name):
            # Safe operation - always allow (controlled by soft restrictions in LLM)
            logger.debug(f"Safe tool '{tool_name}' allowed for role '{role_name}' (no hard check)")
            return True, None

        # Hard check for dangerous tool
        allowed_tools = role_perms.get("allowed_dangerous_tools", [])

        # Wildcard "*" means all dangerous operations allowed
        if allowed_tools == "*":
            logger.debug(f"Dangerous tool '{tool_name}' allowed for role '{role_name}' (wildcard)")
            return True, None

        # Check explicit permission list
        if tool_name in allowed_tools:
            logger.debug(f"Dangerous tool '{tool_name}' allowed for role '{role_name}' (explicit)")
            return True, None

        # Permission denied
        error_message = (
            f"У вас нет прав для этой операции. "
            f"Ваша роль: '{role_name}'. "
            f"Требуется разрешение на '{tool_name}'."
        )
        logger.warning(f"Permission denied: role='{role_name}', tool='{tool_name}'")
        return False, error_message

    def get_soft_restrictions(self, role_name: str) -> Optional[str]:
        """
        Get soft restriction prompt for LLM injection

        Soft restrictions are injected into the system prompt to guide
        the LLM's behavior for safe (read-only) operations.

        Args:
            role_name: User's role name

        Returns:
            Russian text for system prompt injection, or None if no restrictions
        """
        role_name = role_name or "guest"
        role_perms = self.permissions.get(role_name, {})
        soft = role_perms.get("soft_restrictions")

        if soft and isinstance(soft, dict):
            prompt = soft.get("prompt")
            if prompt:
                logger.debug(f"Soft restrictions loaded for role '{role_name}'")
                return prompt

        logger.debug(f"No soft restrictions for role '{role_name}'")
        return None

    def get_role_level(self, role_name: str) -> int:
        """
        Get numeric privilege level of a role

        Higher number = more privileges. Useful for future access level comparisons.

        Args:
            role_name: User's role name

        Returns:
            Numeric level (0-100), 0 for unknown roles
        """
        return self.role_hierarchy.get(role_name, 0)

    def get_allowed_dangerous_tools(self, role_name: str) -> List[str]:
        """
        Get list of dangerous tools allowed for a role

        Args:
            role_name: User's role name

        Returns:
            List of tool names, or ["*"] for wildcard permissions
        """
        role_name = role_name or "guest"
        role_perms = self.permissions.get(role_name, {})
        allowed = role_perms.get("allowed_dangerous_tools", [])

        if allowed == "*":
            return ["*"]  # All dangerous tools
        return allowed if isinstance(allowed, list) else []


# Global singleton instance
rbac_manager = RBACManager()
