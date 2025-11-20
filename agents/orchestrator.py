from pathlib import Path
from typing import List, Optional, Dict, Any
from agents.base import BaseAgent
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage
from core.config import settings
from core.memory import memory_manager
from core.agent_registry import agent_registry
from loguru import logger


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

        # Create ReAct agent with LangGraph
        agent = create_react_agent(
            model=self.llm,
            tools=self.tools,
            state_modifier=self.system_prompt,  # System prompt for the agent (updated for LangGraph 0.2.x)
            checkpointer=checkpointer  # Enable conversation memory
        )

        logger.info(f"ReAct agent created with LangGraph and checkpointer={'enabled' if checkpointer else 'disabled'}")
        return agent

    def process_message(self, user_message: str, thread_id: str = "default", config: Optional[Dict[str, Any]] = None) -> str:
        """
        Process user message with routing to appropriate tools

        Args:
            user_message: User's input message
            thread_id: Thread ID for conversation memory (default: "default")
            config: Optional configuration dict for agent invocation

        Returns:
            Agent's response
        """
        logger.info(f"Processing message in thread '{thread_id}': {user_message[:50]}...")

        try:
            # Prepare config with thread_id for memory persistence
            if config is None:
                config = {}

            # Add thread_id to config if memory is enabled
            if self.checkpointer:
                config["configurable"] = {"thread_id": thread_id}

            # Run agent with LangGraph ReAct pattern
            # Use HumanMessage for proper serialization
            response = self.agent.invoke(
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
