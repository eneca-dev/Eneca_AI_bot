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
        conversation_id: str,
        content: str,
        user_id: str,
        role: str = "assistant",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Insert a message into chat_messages table

        Args:
            conversation_id: Conversation ID (UUID)
            content: Message text
            user_id: User identifier (UUID)
            role: Message role ('user' or 'assistant')
            metadata: Optional metadata dictionary (for backward compat)

        Returns:
            Inserted record or None on failure
        """
        if not self.is_available():
            logger.error("Supabase DB Client not available - cannot insert message")
            return None

        try:
            data = {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "role": role,
                "kind": "message",             # Required field
                "content": content,
                "is_final": True,               # Required field
                "meta": metadata or {}          # Required field (JSONB)
            }

            response = self.client.table("chat_messages").insert(data).execute()

            logger.info(f"Message inserted successfully - conversation: {conversation_id}, role: {role}")
            return response.data[0] if response.data else None

        except Exception as e:
            logger.error(f"Failed to insert message to Supabase: {e}")
            logger.error(f"Data attempted: conversation_id={conversation_id}, role={role}, user_id={user_id}")
            return None

    def get_conversation_history(
        self,
        conversation_id: str,
        limit: int = 20
    ) -> list:
        """
        Get conversation history for a conversation

        Args:
            conversation_id: Conversation ID (UUID)
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
                .eq("conversation_id", conversation_id)
                .order("created_at", desc=False)
                .limit(limit)
                .execute()
            )

            logger.debug(f"Retrieved {len(response.data)} messages for conversation: {conversation_id}")
            return response.data

        except Exception as e:
            logger.error(f"Failed to get conversation history: {e}")
            return []

    def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get user profile with role information from profiles table

        Fetches user profile and role via JOIN with user_roles and roles tables.
        If user has no role assigned, defaults to 'guest' role.

        Args:
            user_id: User ID to fetch profile for

        Returns:
            Dict with profile data including role_name:
            {
                'email': str,
                'first_name': str,
                'last_name': str,
                'role_name': str  # Role name from roles table, 'guest' if not assigned
            }
            Returns None if profile not found or on database error (fail-secure with guest role)
        """
        if not self.is_available():
            logger.warning("Supabase DB Client not available - cannot fetch profile")
            return None

        try:
            # JOIN profiles with user_roles and roles tables
            # SELECT profiles.*, roles.name as role_name
            # FROM profiles
            # LEFT JOIN user_roles ON profiles.user_id = user_roles.user_id
            # LEFT JOIN roles ON user_roles.role_id = roles.id
            response = (
                self.client.table('profiles')
                .select('email, first_name, last_name, user_roles(role_id, roles(name))')
                .eq('user_id', user_id)
                .single()
                .execute()
            )

            if response.data:
                profile = response.data

                # Extract role_name from nested structure
                role_name = 'guest'  # Default role (fail-secure)
                if profile.get('user_roles'):
                    # user_roles is a list of relationships
                    if len(profile['user_roles']) > 0:
                        user_role = profile['user_roles'][0]
                        # roles is nested inside user_role
                        if user_role.get('roles') and user_role['roles'].get('name'):
                            role_name = user_role['roles']['name']
                            logger.debug(f"Role loaded from database: {role_name}")

                # Flatten structure for easier consumption
                result = {
                    'email': profile.get('email'),
                    'first_name': profile.get('first_name'),
                    'last_name': profile.get('last_name'),
                    'role_name': role_name
                }

                logger.info(f"Loaded profile for user_id={user_id}, role={role_name}")
                return result
            else:
                logger.warning(f"No profile found for user_id={user_id}")
                return None

        except Exception as e:
            logger.error(f"Error fetching profile for user_id={user_id}: {e}")
            # Graceful degradation: return guest role on database error (fail-secure)
            logger.warning(f"Returning guest role due to database error")
            return {
                'email': None,
                'first_name': None,
                'last_name': None,
                'role_name': 'guest'
            }


# Global singleton instance
supabase_db_client = SupabaseDBClient()
