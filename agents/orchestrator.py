from pathlib import Path
from typing import List, Optional, Dict, Any
from agents.base import BaseAgent
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage, trim_messages
from core.config import settings
from core.memory import memory_manager
from core.agent_registry import agent_registry
from loguru import logger

# Maximum number of messages to keep in history (prevents token overflow)
MAX_HISTORY_MESSAGES = 20


class OrchestratorAgent(BaseAgent):
    """Main orchestrator agent that handles user queries with routing to specialized agents"""

    def __init__(self, model: str = None, temperature: float = None):
        """Initialize orchestrator agent

        Args:
            model: OpenAI model name (defaults to config value)
            temperature: Response temperature (defaults to config value)
        """
        # Use config defaults if not specified
        model = model or settings.orchestrator_model
        temperature = temperature if temperature is not None else settings.orchestrator_temperature

        super().__init__(model=model, temperature=temperature)

        # Load agents from YAML configuration
        agent_registry.load_from_yaml()

        # Setup tools from registered agents
        self.tools = self._setup_tools()

        # Setup agent with LangGraph create_react_agent
        self.agent = self._setup_agent()

        # Get checkpointer from memory manager
        self.checkpointer = memory_manager.get_checkpointer()

        logger.info(f"OrchestratorAgent initialized with RAG tool and memory={'enabled' if self.checkpointer else 'disabled'}")

    def _get_default_prompt(self) -> str:
        """Load system prompt from prompts/orchestrator.md"""
        prompt_path = Path(__file__).parent.parent / "prompts" / "orchestrator.md"

        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                prompt = f.read()
            logger.debug(f"Loaded prompt from {prompt_path}")
            return prompt
        except FileNotFoundError:
            logger.warning(f"Prompt file not found at {prompt_path}, using default")
            return "You are a helpful AI assistant that routes queries to appropriate tools."

    def _setup_tools(self) -> List:
        """Setup tools for the orchestrator from registered agents"""
        # Get tools automatically from all registered agents
        tools = agent_registry.create_tools_for_agents()
        logger.info(f"Setup {len(tools)} tools for orchestrator from AgentRegistry")
        return tools

    def _setup_agent(self):
        """Setup LangGraph ReAct agent with checkpointer"""
        # Get checkpointer from memory manager
        checkpointer = memory_manager.get_checkpointer()

        # Create ReAct agent with LangGraph 1.0
        # Note: 'prompt' replaces 'state_modifier' in LangGraph 1.0
        agent = create_react_agent(
            model=self.llm,
            tools=self.tools,
            prompt=self.system_prompt,  # System prompt for the agent (LangGraph 1.0 API)
            checkpointer=checkpointer  # Enable conversation memory
        )

        logger.info(f"ReAct agent created with LangGraph and checkpointer={'enabled' if checkpointer else 'disabled'}")
        return agent

    def process_message(
        self,
        user_message: str,
        thread_id: str = "default",
        config: Optional[Dict[str, Any]] = None,
        user_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Process user message with routing to appropriate tools

        Args:
            user_message: User's input message
            thread_id: Thread ID for conversation memory (default: "default")
            config: Optional configuration dict for agent invocation
            user_context: Optional user profile context:
                - email: str
                - first_name: str
                - last_name: str
                - job_title: str (optional)
                - department: str (optional)
                - role_name: str (for RBAC)

        Returns:
            Agent's response
        """
        from core.agent_registry import set_current_user_role

        logger.info(f"Processing message in thread '{thread_id}': {user_message[:50]}...")

        # Set current user role in thread-local storage for agents (RBAC)
        user_role = user_context.get('role_name') if user_context else None
        set_current_user_role(user_role)
        logger.info(f"User role for this request: {user_role or 'guest'}")

        try:
            # Prepare config with thread_id for memory persistence
            if config is None:
                config = {}

            # Add thread_id to config if memory is enabled
            if self.checkpointer:
                config["configurable"] = {"thread_id": thread_id}

            # Build effective system prompt with user context
            effective_system_prompt = self.system_prompt

            if user_context:
                # Add user context to system prompt
                context_text = self._format_user_context(user_context)
                if context_text:  # Only add if context is not empty
                    effective_system_prompt = f"{self.system_prompt}\n\n{context_text}"
                    logger.info(f"Added user context to system prompt for thread '{thread_id}'")

            # Create prompt function that:
            # 1. Trims history to prevent token overflow
            # 2. Adds system prompt with user context
            # Note: In LangGraph 1.0, 'prompt' replaces 'state_modifier'
            def prompt_fn(state):
                """Prepare messages for LLM: trim history + add system prompt"""
                messages = state.get("messages", [])

                # Trim messages to last N to prevent token overflow
                trimmed = trim_messages(
                    messages,
                    max_tokens=MAX_HISTORY_MESSAGES,  # Using count, not actual tokens
                    strategy="last",
                    token_counter=len,  # Count messages, not tokens
                    start_on="human",  # Start from human message
                    include_system=True,
                    allow_partial=False,
                )

                # Log trimming info
                if len(messages) > len(trimmed):
                    logger.debug(f"Trimmed history: {len(messages)} -> {len(trimmed)} messages")

                # Add system prompt at the beginning
                return [{"role": "system", "content": effective_system_prompt}] + list(trimmed)

            # Create temporary agent with prompt function
            # LangGraph agents are lightweight, OK to recreate for each message
            temp_agent = create_react_agent(
                model=self.llm,
                tools=self.tools,
                prompt=prompt_fn,  # Function that trims + adds system prompt (LangGraph 1.0 API)
                checkpointer=self.checkpointer
            )

            # Run agent with user message
            response = temp_agent.invoke(
                {"messages": [HumanMessage(content=user_message)]},
                config=config
            )

            # Debug: log response structure
            logger.debug(f"Agent response type: {type(response)}")
            logger.debug(f"Agent response keys: {response.keys() if isinstance(response, dict) else 'N/A'}")
            if isinstance(response, dict) and "messages" in response:
                logger.debug(f"Messages count: {len(response['messages'])}")
                logger.debug(f"Last message type: {type(response['messages'][-1])}")

            # Extract output from messages
            if isinstance(response, dict) and "messages" in response:
                # Get last message content
                last_message = response["messages"][-1]

                # Handle different message types
                if hasattr(last_message, 'content'):
                    # AIMessage or similar object
                    output = str(last_message.content)
                    logger.debug(f"Extracted output from AIMessage: {output[:100]}...")
                elif isinstance(last_message, dict):
                    # Dict message
                    output = str(last_message.get("content", "Не удалось получить ответ."))
                    logger.debug(f"Extracted output from dict: {output[:100]}...")
                else:
                    # Fallback
                    output = str(last_message)
                    logger.debug(f"Extracted output from fallback: {output[:100]}...")
            else:
                # If response is not in expected format
                output = str(response)
                logger.debug(f"Extracted output from str(response): {output[:100]}...")

            # Ensure output is a string
            if not isinstance(output, str):
                output = str(output)

            logger.info(f"Message processed successfully in thread '{thread_id}' - Output length: {len(output)}")
            return output

        except Exception as e:
            logger.error(f"Error processing message in thread '{thread_id}': {e}")
            return (
                "Произошла ошибка при обработке вашего запроса. "
                "Пожалуйста, попробуйте переформулировать вопрос."
            )
        finally:
            # Clear user role from thread-local storage after processing (RBAC cleanup)
            set_current_user_role(None)
            logger.debug("Cleared thread-local user role")

    def _format_user_context(self, user_context: Dict[str, Any]) -> str:
        """
        Format user context for system prompt injection

        Includes user profile data and role-based soft restrictions for LLM.

        Args:
            user_context: Dict with user profile data:
                - email: str
                - first_name: str
                - last_name: str
                - job_title: str (optional)
                - department: str (optional)
                - role_name: str (for RBAC)

        Returns:
            Formatted context string for system prompt in Russian
        """
        from core.rbac import rbac_manager

        parts = ["=== КОНТЕКСТ ПОЛЬЗОВАТЕЛЯ ==="]

        # Add name if available
        if user_context.get('first_name') or user_context.get('last_name'):
            name = f"{user_context.get('first_name', '')} {user_context.get('last_name', '')}".strip()
            parts.append(f"Имя пользователя: {name}")

        # Add job title
        if user_context.get('job_title'):
            parts.append(f"Должность: {user_context['job_title']}")

        # Add department
        if user_context.get('department'):
            parts.append(f"Отдел: {user_context['department']}")

        # Add email
        if user_context.get('email'):
            parts.append(f"Email: {user_context['email']}")

        # Add role (NEW - RBAC integration)
        role_name = user_context.get('role_name', 'guest')
        parts.append(f"Роль: {role_name}")

        # If only header (no actual data), return empty string
        if len(parts) == 1:
            return ""

        parts.append("=== КОНЕЦ КОНТЕКСТА ===")

        # Add soft restrictions for LLM (NEW - RBAC soft control)
        soft_restrictions = rbac_manager.get_soft_restrictions(role_name)
        if soft_restrictions:
            parts.append("")  # Empty line for spacing
            parts.append("=== ОГРАНИЧЕНИЯ ДОСТУПА ===")
            parts.append(soft_restrictions)
            parts.append("=== КОНЕЦ ОГРАНИЧЕНИЙ ===")

        return "\n".join(parts)
