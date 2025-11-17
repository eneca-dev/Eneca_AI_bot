from pathlib import Path
from typing import List
from agents.base import BaseAgent
from agents.rag_agent import RAGAgent
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import Tool
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.schema import SystemMessage
from loguru import logger


class OrchestratorAgent(BaseAgent):
    """Main orchestrator agent that handles user queries with routing to specialized agents"""

    def __init__(self, model: str = "gpt-5-mini", temperature: float = 0.7):
        """Initialize orchestrator agent"""
        super().__init__(model=model, temperature=temperature)

        # Initialize RAG agent
        self.rag_agent = RAGAgent()

        # Setup tools
        self.tools = self._setup_tools()

        # Setup agent executor
        self.agent_executor = self._setup_agent_executor()

        logger.info("OrchestratorAgent initialized with RAG tool")

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

    def _setup_tools(self) -> List[Tool]:
        """Setup tools for the orchestrator"""
        tools = [
            Tool(
                name="knowledge_search",
                description=(
                    "Используй этот инструмент для поиска информации в базе знаний. "
                    "Подходит для вопросов о функционале приложения, инструкций, "
                    "документации и любой специфической информации о системе. "
                    "Вход: запрос пользователя (строка). "
                    "Выход: релевантная информация из базы знаний."
                ),
                func=self.rag_agent.answer_question,
            )
        ]

        logger.info(f"Setup {len(tools)} tools for orchestrator")
        return tools

    def _setup_agent_executor(self) -> AgentExecutor:
        """Setup LangChain agent executor with tools"""
        # Create prompt template
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.system_prompt),
            MessagesPlaceholder(variable_name="chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])

        # Create agent
        agent = create_openai_functions_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=prompt
        )

        # Create agent executor
        agent_executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=True,
            max_iterations=5,
            early_stopping_method="generate",
            handle_parsing_errors=True,
        )

        logger.info("Agent executor created successfully")
        return agent_executor

    def process_message(self, user_message: str) -> str:
        """
        Process user message with routing to appropriate tools

        Args:
            user_message: User's input message

        Returns:
            Agent's response
        """
        logger.info(f"Processing message: {user_message[:50]}...")

        try:
            # Run agent executor
            response = self.agent_executor.invoke({
                "input": user_message,
            })

            # Extract output
            output = response.get("output", "Не удалось получить ответ.")

            logger.info("Message processed successfully")
            return output

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return (
                "Произошла ошибка при обработке вашего запроса. "
                "Пожалуйста, попробуйте переформулировать вопрос."
            )
