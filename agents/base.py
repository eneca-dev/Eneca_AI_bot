from abc import ABC, abstractmethod
from typing import Optional
from langchain_openai import ChatOpenAI
from langchain.schema import SystemMessage, HumanMessage, AIMessage
from core.config import settings
from loguru import logger


class BaseAgent(ABC):
    """Base class for all agents"""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        system_prompt: Optional[str] = None
    ):
        """
        Initialize base agent

        Args:
            model: OpenAI model name
            temperature: Response temperature (0-1)
            system_prompt: System prompt for the agent
        """
        self.model = model
        self.temperature = temperature
        self.system_prompt = system_prompt or self._get_default_prompt()

        # Initialize LangChain ChatOpenAI
        self.llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            openai_api_key=settings.openai_api_key
        )

        logger.info(f"Initialized {self.__class__.__name__} with model {model}")

    @abstractmethod
    def _get_default_prompt(self) -> str:
        """Get default system prompt for this agent"""
        pass

    def invoke(self, user_message: str) -> str:
        """
        Process user message and return response

        Args:
            user_message: User's input message

        Returns:
            Agent's response
        """
        try:
            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=user_message)
            ]

            logger.debug(f"Invoking {self.__class__.__name__} with message: {user_message}")

            response = self.llm.invoke(messages)

            logger.debug(f"Response from {self.__class__.__name__}: {response.content}")

            return response.content

        except Exception as e:
            logger.error(f"Error in {self.__class__.__name__}.invoke: {e}")
            raise
