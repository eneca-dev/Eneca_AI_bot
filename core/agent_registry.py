"""Agent Registry for dynamic agent management"""
from typing import Dict, List, Any, Optional, Type, Callable
from pathlib import Path
import importlib
import inspect
import threading
import yaml
from dataclasses import dataclass
from agents.base import BaseAgent
from core.config import settings
from loguru import logger


# Thread-local storage for current user role (RBAC integration)
_current_user_role = threading.local()


def set_current_user_role(role: Optional[str]):
    """
    Set current user role in thread-local storage

    Used by orchestrator to pass user role to agents for permission checking.
    Thread-local ensures isolation between concurrent requests.

    Args:
        role: User's role name (e.g., "admin", "manager", "guest")
    """
    _current_user_role.value = role
    logger.debug(f"Set thread-local user role: {role}")


def get_current_user_role() -> Optional[str]:
    """
    Get current user role from thread-local storage

    Returns:
        User's role name, or None if not set
    """
    return getattr(_current_user_role, 'value', None)


@dataclass
class AgentConfig:
    """Configuration for a registered agent"""
    name: str
    class_path: str  # e.g., "agents.rag_agent.RAGAgent"
    enabled: bool
    description: str
    tool_description: str  # Description for the tool in Russian
    config: Dict[str, Any]  # Agent-specific configuration
    priority: int = 0  # Higher priority agents are registered first


class AgentRegistry:
    """Registry for managing agents dynamically"""

    def __init__(self):
        """Initialize the agent registry"""
        self._agents: Dict[str, AgentConfig] = {}
        self._agent_instances: Dict[str, BaseAgent] = {}
        self._config_file = Path(__file__).parent.parent / "config" / "agents.yaml"

        logger.info("AgentRegistry initialized")

    def register_agent(
        self,
        name: str,
        class_path: str,
        description: str,
        tool_description: str,
        enabled: bool = True,
        config: Optional[Dict[str, Any]] = None,
        priority: int = 0
    ) -> None:
        """
        Register an agent

        Args:
            name: Unique identifier for the agent
            class_path: Full import path to agent class (e.g., "agents.rag_agent.RAGAgent")
            description: Human-readable description of the agent
            tool_description: Tool description in Russian for LLM
            enabled: Whether the agent is enabled
            config: Agent-specific configuration
            priority: Registration priority (higher = first)
        """
        if name in self._agents:
            logger.warning(f"Agent '{name}' already registered, overwriting")

        agent_config = AgentConfig(
            name=name,
            class_path=class_path,
            enabled=enabled,
            description=description,
            tool_description=tool_description,
            config=config or {},
            priority=priority
        )

        self._agents[name] = agent_config
        logger.info(f"Registered agent: {name} (enabled={enabled}, priority={priority})")

    def unregister_agent(self, name: str) -> None:
        """Unregister an agent"""
        if name in self._agents:
            del self._agents[name]
            if name in self._agent_instances:
                del self._agent_instances[name]
            logger.info(f"Unregistered agent: {name}")
        else:
            logger.warning(f"Agent '{name}' not found in registry")

    def get_agent(self, name: str) -> Optional[BaseAgent]:
        """
        Get agent instance (creates if not exists)

        Args:
            name: Agent name

        Returns:
            Agent instance or None if not found/enabled
        """
        if name not in self._agents:
            logger.warning(f"Agent '{name}' not found in registry")
            return None

        agent_config = self._agents[name]

        if not agent_config.enabled:
            logger.warning(f"Agent '{name}' is disabled")
            return None

        # Return cached instance if exists
        if name in self._agent_instances:
            return self._agent_instances[name]

        # Create new instance
        try:
            agent_instance = self._create_agent_instance(agent_config)
            self._agent_instances[name] = agent_instance
            logger.info(f"Created instance for agent: {name}")
            return agent_instance
        except Exception as e:
            logger.error(f"Failed to create agent '{name}': {e}")
            return None

    def _create_agent_instance(self, agent_config: AgentConfig) -> BaseAgent:
        """
        Create agent instance from configuration

        Args:
            agent_config: Agent configuration

        Returns:
            Agent instance
        """
        # Parse class path (e.g., "agents.rag_agent.RAGAgent")
        module_path, class_name = agent_config.class_path.rsplit('.', 1)

        # Import module and get class
        module = importlib.import_module(module_path)
        agent_class: Type[BaseAgent] = getattr(module, class_name)

        # Create instance with config
        agent_instance = agent_class(**agent_config.config)

        return agent_instance

    def list_agents(self, enabled_only: bool = True) -> List[str]:
        """
        List all registered agent names

        Args:
            enabled_only: Only return enabled agents

        Returns:
            List of agent names
        """
        if enabled_only:
            return [
                name for name, config in self._agents.items()
                if config.enabled
            ]
        return list(self._agents.keys())

    def get_agent_config(self, name: str) -> Optional[AgentConfig]:
        """Get agent configuration"""
        return self._agents.get(name)

    def get_all_configs(self, enabled_only: bool = True) -> List[AgentConfig]:
        """
        Get all agent configurations

        Args:
            enabled_only: Only return enabled agents

        Returns:
            List of agent configurations sorted by priority (descending)
        """
        configs = [
            config for config in self._agents.values()
            if not enabled_only or config.enabled
        ]
        # Sort by priority (higher priority first)
        return sorted(configs, key=lambda c: c.priority, reverse=True)

    def load_from_yaml(self, config_path: Optional[Path] = None) -> None:
        """
        Load agent configurations from YAML file

        Args:
            config_path: Path to YAML config file (defaults to config/agents.yaml)
        """
        config_path = config_path or self._config_file

        if not config_path.exists():
            logger.warning(f"Agent config file not found: {config_path}")
            return

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            if not data or 'agents' not in data:
                logger.warning(f"No agents found in {config_path}")
                return

            for agent_data in data['agents']:
                self.register_agent(
                    name=agent_data['name'],
                    class_path=agent_data['class_path'],
                    description=agent_data.get('description', ''),
                    tool_description=agent_data.get('tool_description', ''),
                    enabled=agent_data.get('enabled', True),
                    config=agent_data.get('config', {}),
                    priority=agent_data.get('priority', 0)
                )

            logger.info(f"Loaded {len(data['agents'])} agents from {config_path}")

        except Exception as e:
            logger.error(f"Failed to load agent config from {config_path}: {e}")

    def create_tools_for_agents(self) -> List[Callable]:
        """
        Create LangChain tools for all enabled agents

        Returns:
            List of tool functions
        """
        from langchain_core.tools import tool

        tools = []
        configs = self.get_all_configs(enabled_only=True)

        for agent_config in configs:
            agent_instance = self.get_agent(agent_config.name)
            if not agent_instance:
                continue

            # Create a closure to capture agent_instance
            def make_tool_func(agent_inst, agent_name):
                def tool_func(query: str) -> str:
                    """Tool function that calls the agent with optional user_role from thread-local"""
                    # DEBUG: Log tool invocation
                    logger.info(f"🔧 TOOL CALLED: '{agent_name}' with query: '{query[:100]}...'")

                    try:
                        # Get current user role from thread-local storage (RBAC integration)
                        user_role = get_current_user_role()

                        # Try passing user_role if method signature supports it
                        if hasattr(agent_inst, 'answer_question'):
                            sig = inspect.signature(agent_inst.answer_question)
                            if 'user_role' in sig.parameters:
                                logger.debug(f"Calling {agent_name}.answer_question with user_role={user_role}")
                                result = agent_inst.answer_question(query, user_role=user_role)
                            else:
                                result = agent_inst.answer_question(query)
                        elif hasattr(agent_inst, 'process_message'):
                            sig = inspect.signature(agent_inst.process_message)
                            if 'user_role' in sig.parameters:
                                logger.debug(f"Calling {agent_name}.process_message with user_role={user_role}")
                                result = agent_inst.process_message(query, user_role=user_role)
                            else:
                                result = agent_inst.process_message(query)
                        else:
                            return f"Агент '{agent_name}' не поддерживает обработку запросов"

                        # DEBUG: Log tool result
                        logger.info(f"🔧 TOOL RESULT from '{agent_name}': {len(result)} chars")
                        logger.debug(f"🔧 TOOL RESULT preview: '{result[:200]}...'")

                        return result
                    except Exception as e:
                        logger.error(f"Error in tool for agent '{agent_name}': {e}")
                        return f"Ошибка при вызове агента '{agent_name}': {str(e)}"

                return tool_func

            # Create tool with proper metadata
            tool_func = make_tool_func(agent_instance, agent_config.name)
            tool_func.__name__ = agent_config.name
            tool_func.__doc__ = agent_config.tool_description

            # Decorate with @tool
            tool_instance = tool(tool_func)
            tools.append(tool_instance)

            logger.info(f"Created tool for agent: {agent_config.name}")

        return tools


# Global registry instance
agent_registry = AgentRegistry()
