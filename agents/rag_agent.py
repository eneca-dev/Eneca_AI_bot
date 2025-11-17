"""RAG Agent for knowledge base search"""
from pathlib import Path
from typing import List, Dict
from agents.base import BaseAgent
from core.vector_store import vector_store_manager
from core.config import settings
from loguru import logger


class RAGAgent(BaseAgent):
    """RAG Agent that searches knowledge base and provides factual answers"""

    def __init__(self, model: str = None, temperature: float = None):
        """
        Initialize RAG agent

        Args:
            model: OpenAI model name (defaults to config value)
            temperature: Lower temperature for more factual responses (defaults to config value)
        """
        # Use config defaults if not specified
        model = model or settings.rag_agent_model
        temperature = temperature if temperature is not None else settings.rag_agent_temperature

        super().__init__(model=model, temperature=temperature)
        self.vector_store = vector_store_manager
        logger.info(f"RAGAgent initialized with model {model} and temperature {temperature}")

    def _get_default_prompt(self) -> str:
        """Load system prompt from prompts/rag_agent.md"""
        prompt_path = Path(__file__).parent.parent / "prompts" / "rag_agent.md"

        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                prompt = f.read()
            logger.debug(f"Loaded RAG agent prompt from {prompt_path}")
            return prompt
        except FileNotFoundError:
            logger.warning(f"Prompt file not found at {prompt_path}, using default")
            return (
                "You are a RAG agent. Search the knowledge base and provide accurate, "
                "factual answers based only on the information found in the documents."
            )

    def search_knowledge_base(self, query: str, k: int = None) -> str:
        """
        Search knowledge base and return formatted results

        Args:
            query: User's search query
            k: Number of results to return (defaults to config value)

        Returns:
            Formatted string with search results
        """
        if not self.vector_store.is_available():
            logger.warning("Vector store not available")
            return (
                "База знаний временно недоступна. "
                "Пожалуйста, попробуйте позже или обратитесь к администратору."
            )

        try:
            # Search with relevance scores (uses config defaults if k not provided)
            documents = self.vector_store.search_with_score(query=query, k=k)

            if not documents:
                return "Информация по вашему запросу не найдена в базе знаний."

            # Format results
            result = "Найденная информация:\n\n"
            for i, doc in enumerate(documents, 1):
                content = doc["content"]
                score = doc.get("score", 0)
                relevance = doc.get("relevance", "unknown")

                result += f"[Документ {i}] (релевантность: {relevance}, score: {score:.2f})\n"
                result += f"{content}\n\n"

            return result.strip()

        except Exception as e:
            logger.error(f"Error searching knowledge base: {e}")
            return (
                "Произошла ошибка при поиске в базе знаний. "
                "Пожалуйста, попробуйте переформулировать запрос."
            )

    def answer_question(self, question: str) -> str:
        """
        Answer user question using RAG approach

        Args:
            question: User's question

        Returns:
            Answer based on knowledge base
        """
        logger.info(f"RAG Agent processing question: {question[:50]}...")

        # Search knowledge base
        context = self.search_knowledge_base(question)

        # If no relevant documents found, return early
        if "не найдена" in context or "недоступна" in context or "ошибка" in context.lower():
            return context

        # Construct prompt with context
        prompt_with_context = f"""На основе следующей информации из базы знаний ответь на вопрос пользователя.

ВАЖНО: Используй ТОЛЬКО информацию из предоставленного контекста. Не придумывай и не добавляй информацию извне.

Контекст из базы знаний:
{context}

Вопрос пользователя: {question}

Твой ответ должен:
1. Быть основан только на информации из контекста выше
2. Быть чётким и структурированным
3. Если информация неполная — прямо об этом сказать
4. Быть на русском языке
"""

        # Get answer from LLM
        try:
            response = self.invoke(prompt_with_context)
            logger.info("RAG Agent successfully generated answer")
            return response

        except Exception as e:
            logger.error(f"Error generating answer: {e}")
            return (
                "Не удалось сформировать ответ. "
                "Пожалуйста, попробуйте переформулировать вопрос."
            )

    def process_message(self, user_message: str) -> str:
        """
        Process user message (alias for answer_question)

        Args:
            user_message: User's input message

        Returns:
            Agent's response
        """
        return self.answer_question(user_message)
