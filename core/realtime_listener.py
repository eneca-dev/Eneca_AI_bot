"""
Chat Messages Polling Listener
Polls Supabase chat_messages table for new user messages
(Polling-based alternative to Realtime since supabase-py has limited async support)

Architecture (Variant C - Hybrid):
- Checkpointer = memory for LLM (single source of truth for history)
- chat_messages = UI log (write-only from bot, no read for history)
"""
import time
import threading
from typing import Optional, Set
from datetime import datetime
from loguru import logger
from supabase import create_client, Client
from core.config import settings
from agents.orchestrator import OrchestratorAgent
from database.supabase_client import supabase_db_client


class RealtimeListener:
    """
    Polling-based listener for chat_messages table
    Checks for new user messages every N seconds

    Note: Named "RealtimeListener" for API compatibility but uses polling internally
    since supabase-py doesn't have good async Realtime support
    """

    def __init__(self, agent: OrchestratorAgent):
        self.agent = agent
        self.client: Optional[Client] = None
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self._processed_ids: Set[str] = set()  # Track processed message IDs
        self._poll_interval = 2  # Poll every 2 seconds
        self._start_time = datetime.utcnow()  # Only process messages after bot starts

    def start(self):
        """Start polling listener in background thread"""
        if self.running:
            logger.warning("Realtime listener already running")
            return

        try:
            # Initialize Supabase client with SERVICE_ROLE_KEY (bypasses RLS)
            # NOTE: Using SERVICE_ROLE_KEY because ANON_KEY may be blocked by RLS policies
            self.client = create_client(
                settings.supabase_chat_url,
                settings.supabase_chat_service_key  # SERVICE_ROLE_KEY bypasses RLS
            )

            self.running = True

            # Start polling in background thread
            self._thread = threading.Thread(target=self._poll_messages, daemon=True)
            self._thread.start()

            logger.info(f"✅ Polling listener started - checking for new messages every {self._poll_interval}s")

        except Exception as e:
            logger.error(f"Failed to start polling listener: {e}")
            raise

    def _poll_messages(self):
        """Poll for new messages in background thread"""
        while self.running:
            try:
                # Calculate cutoff time (messages created after bot started)
                cutoff_time = self._start_time.strftime("%Y-%m-%dT%H:%M:%S")

                # Query for new user messages created after bot started
                # Note: We query recent messages and filter by _processed_ids
                # Using desc=True to get LATEST messages first, then process oldest-first
                response = self.client.table('chat_messages')\
                    .select('*')\
                    .eq('role', 'user')\
                    .gte('created_at', cutoff_time)\
                    .order('created_at', desc=True)\
                    .limit(50)\
                    .execute()

                if response.data:
                    # Reverse to process oldest-first (we queried desc=True for latest)
                    messages_to_process = list(reversed(response.data))

                    # Count new messages (not in _processed_ids)
                    new_count = sum(1 for m in messages_to_process if m['id'] not in self._processed_ids)
                    if new_count > 0:
                        logger.info(f"📬 {new_count} NEW messages to process (out of {len(messages_to_process)} total)")

                    for message in messages_to_process:
                        message_id = message['id']

                        # Skip if already processed
                        if message_id in self._processed_ids:
                            continue

                        # Mark as processed BEFORE handling (prevent duplicates)
                        self._processed_ids.add(message_id)

                        # Handle the message
                        self._handle_message(message)

                    # Clean old IDs from set (keep only last 500 to handle high volume)
                    if len(self._processed_ids) > 500:
                        # Convert to list, sort, keep last 500
                        sorted_ids = sorted(self._processed_ids)
                        self._processed_ids = set(sorted_ids[-500:])

            except Exception as e:
                logger.error(f"Error polling messages: {e}")

            # Sleep before next poll
            time.sleep(self._poll_interval)

    def _handle_message(self, record: dict):
        """
        Handle new user message.

        Architecture (Variant C - Hybrid):
        - Checkpointer = memory for LLM (single source of truth for history)
        - chat_messages = UI log (write-only, no read for history)

        This prevents double history loading and token overflow.
        """
        try:
            conversation_id = record['conversation_id']
            user_message = record['content']
            user_id = record['user_id']

            logger.info(f"📨 Processing message from conversation: {conversation_id}, user_id: {user_id}")
            logger.debug(f"📋 Full record: {record}")

            # Fetch user profile for context injection
            user_context = None
            if user_id and supabase_db_client.is_available():
                user_context = supabase_db_client.get_user_profile(user_id)
                if user_context:
                    logger.info(f"👤 Loaded profile: {user_context.get('first_name', '')} {user_context.get('last_name', '')} (role: {user_context.get('role_name', 'guest')})")

            # NOTE: We do NOT load history from chat_messages anymore!
            # Checkpointer handles history automatically via thread_id.
            # This prevents double history (chat_messages + checkpointer) that caused token overflow.

            logger.info(f"📤 Sending message to agent (history managed by checkpointer)")

            # Use orchestrator's process_message which handles:
            # - Checkpointer for history (via thread_id = conversation_id)
            # - User context injection
            # - RBAC role setting
            bot_response = self.agent.process_message(
                user_message=user_message,
                thread_id=conversation_id,
                user_context=user_context
            )

            logger.info(f"🤖 Generated response (length: {len(bot_response)} chars)")

            # Write bot response to chat_messages (for UI display)
            if supabase_db_client.is_available():
                result = supabase_db_client.insert_message(
                    conversation_id=conversation_id,
                    content=bot_response,
                    user_id=user_id,
                    role='assistant',
                    metadata=record.get('metadata')
                )
                if result:
                    logger.success(f"✅ Response sent for conversation: {conversation_id}, message_id: {result.get('id')}")
                else:
                    logger.error(f"❌ Failed to insert response for conversation: {conversation_id}")
            else:
                logger.error("Supabase DB client unavailable - cannot write response")

        except Exception as e:
            logger.error(f"Error handling message: {e}")
            # Write error message to chat
            try:
                if supabase_db_client.is_available():
                    supabase_db_client.insert_message(
                        conversation_id=record['conversation_id'],
                        content="Извините, произошла ошибка при обработке вашего сообщения.",
                        user_id=record['user_id'],
                        role='assistant'
                    )
            except:
                pass  # Silently fail if error message can't be written

    def stop(self):
        """Stop polling listener"""
        if not self.running:
            return

        self.running = False

        # Wait for thread to finish (with timeout)
        if self._thread:
            self._thread.join(timeout=5.0)

        logger.info("Polling listener stopped")


# Global singleton instance (will be initialized in app.py lifespan)
realtime_listener: Optional[RealtimeListener] = None
