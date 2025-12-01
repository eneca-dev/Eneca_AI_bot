"""
Supabase Database Client for PROD chat_messages table

Uses PROD PROJECT SERVICE_ROLE_KEY to write bot responses to database.
Separate from vector_store.py which uses DEV PROJECT ANON_KEY for RAG.
"""

from typing import Optional, Dict, Any
from supabase import create_client, Client
from loguru import logger
from core.config import settings


class SupabaseDBClient:
    """Singleton Supabase client for chat_messages table operations"""

    def __init__(self):
        self.client: Optional[Client] = None
        self._initialize()

    def _initialize(self):
        """Initialize Supabase client with PROD PROJECT SERVICE_ROLE_KEY"""
        try:
            if not settings.supabase_chat_url or not settings.supabase_chat_service_key:
                logger.warning("PROD Supabase credentials not configured - database writes disabled")
                self.client = None
                return

            # Create client with PROD SERVICE_ROLE_KEY to bypass RLS
            self.client = create_client(
                settings.supabase_chat_url,
                settings.supabase_chat_service_key
            )

            logger.info("Supabase DB Client initialized with PROD SERVICE_ROLE_KEY")

        except Exception as e:
            logger.error(f"Failed to initialize Supabase DB Client: {e}")
            self.client = None

    def is_available(self) -> bool:
        """Check if Supabase client is available"""
        return self.client is not None

    def insert_message(
        self,
        thread_id: str,
        content: str,
        user_id: str,
        role: str = "assistant",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Insert a message into chat_messages table

        Args:
            thread_id: Conversation thread ID
            content: Message text
            user_id: User identifier
            role: Message role ('user' or 'assistant')
            metadata: Optional metadata dictionary

        Returns:
            Inserted record or None on failure
        """
        if not self.is_available():
            logger.error("Supabase DB Client not available - cannot insert message")
            return None

        try:
            data = {
                "thread_id": thread_id,
                "content": content,
                "user_id": user_id,
                "role": role,
                "metadata": metadata or {}
            }

            response = self.client.table("chat_messages").insert(data).execute()

            logger.info(f"Message inserted successfully - thread: {thread_id}, role: {role}")
            return response.data[0] if response.data else None

        except Exception as e:
            logger.error(f"Failed to insert message to Supabase: {e}")
            logger.error(f"Data attempted: thread_id={thread_id}, role={role}, user_id={user_id}")
            return None

    def get_conversation_history(
        self,
        thread_id: str,
        limit: int = 20
    ) -> list:
        """
        Get conversation history for a thread

        Args:
            thread_id: Conversation thread ID
            limit: Maximum number of messages to retrieve

        Returns:
            List of messages ordered by created_at
        """
        if not self.is_available():
            logger.error("Supabase DB Client not available")
            return []

        try:
            response = (
                self.client.table("chat_messages")
                .select("*")
                .eq("thread_id", thread_id)
                .order("created_at", desc=False)
                .limit(limit)
                .execute()
            )

            logger.debug(f"Retrieved {len(response.data)} messages for thread: {thread_id}")
            return response.data

        except Exception as e:
            logger.error(f"Failed to get conversation history: {e}")
            return []


# Global singleton instance
supabase_db_client = SupabaseDBClient()
