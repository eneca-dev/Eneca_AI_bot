"""Memory management module for conversation state persistence"""
from pathlib import Path
from typing import Optional
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from core.config import settings
from loguru import logger


class MemoryManager:
    """Manager for conversation memory and checkpointing

    Supports two memory backends:
    - memory: In-memory (fast, but lost on restart)
    - sqlite: SQLite database (persistent across restarts)
    """

    def __init__(self):
        """Initialize memory manager based on configuration"""
        self.checkpointer = None
        self._context_manager = None  # Keep reference to context manager for SQLite
        self._initialize()

    def _initialize(self):
        """Initialize checkpointer based on memory_type setting"""
        logger.debug(f"Memory config: enable={settings.enable_conversation_memory}, type={settings.memory_type}")

        if not settings.enable_conversation_memory:
            logger.info("Conversation memory is disabled")
            return

        memory_type = settings.memory_type.lower()

        try:
            if memory_type == "memory":
                # In-memory checkpointer (not persistent across restarts)
                self.checkpointer = InMemorySaver()
                logger.info("Initialized InMemorySaver for conversation memory")

            elif memory_type == "sqlite":
                # SQLite checkpointer (persistent to disk)
                db_path = Path(settings.memory_db_path)
                db_path.parent.mkdir(parents=True, exist_ok=True)

                # SqliteSaver.from_conn_string returns a context manager
                # Keep reference to prevent connection from closing
                self._context_manager = SqliteSaver.from_conn_string(str(db_path))
                self.checkpointer = self._context_manager.__enter__()
                logger.info(f"Initialized SqliteSaver with database at {db_path}")

            else:
                logger.warning(f"Unknown memory_type '{memory_type}', using InMemorySaver")
                self.checkpointer = InMemorySaver()

        except Exception as e:
            logger.error(f"Error initializing memory manager: {e}")
            logger.warning("Falling back to InMemorySaver")
            self.checkpointer = InMemorySaver()

    def get_checkpointer(self) -> Optional[InMemorySaver]:
        """
        Get the configured checkpointer

        Returns:
            Checkpointer instance or None if memory is disabled
        """
        return self.checkpointer

    def is_enabled(self) -> bool:
        """Check if conversation memory is enabled"""
        return self.checkpointer is not None


# Global memory manager instance
memory_manager = MemoryManager()
