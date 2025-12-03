"""
Chat Messages Polling Listener
Polls Supabase chat_messages table for new user messages
(Polling-based alternative to Realtime since supabase-py has limited async support)
"""
import time
import threading
from typing import Optional, Set
from datetime import datetime, timedelta
from loguru import logger
from supabase import create_client, Client
from langchain_core.messages import HumanMessage, AIMessage
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
                response = self.client.table('chat_messages')\
                    .select('*')\
                    .eq('role', 'user')\
                    .gte('created_at', cutoff_time)\
                    .order('created_at', desc=False)\
                    .limit(10)\
                    .execute()

                # Debug logging
                logger.info(f"🔍 Polling check - Found {len(response.data) if response.data else 0} new user messages since {cutoff_time}")

                if response.data:
                    for message in response.data:
                        message_id = message['id']

                        # Skip if already processed
                        if message_id in self._processed_ids:
                            continue

                        # Mark as processed BEFORE handling (prevent duplicates)
                        self._processed_ids.add(message_id)

                        # Handle the message
                        self._handle_message(message)

                        # Clean old IDs from set (keep only last 100)
                        if len(self._processed_ids) > 100:
                            self._processed_ids = set(list(self._processed_ids)[-100:])

            except Exception as e:
                logger.error(f"Error polling messages: {e}")

            # Sleep before next poll
            time.sleep(self._poll_interval)

    def _handle_message(self, record: dict):
        """
        Handle new user message
        Loads conversation history from chat_messages table and processes with agent
        """
        try:
            conversation_id = record['conversation_id']
            user_message = record['content']
            user_id = record['user_id']

            logger.info(f"📨 Processing message from conversation: {conversation_id}")

            # Load conversation history from Supabase
            messages = []
            if supabase_db_client.is_available():
                history = supabase_db_client.get_conversation_history(conversation_id, limit=20)
                for msg in history:
                    if msg.get('role') == 'user':
                        messages.append(HumanMessage(content=msg.get('content', '')))
                    elif msg.get('role') == 'assistant':
                        messages.append(AIMessage(content=msg.get('content', '')))
                logger.info(f"📜 Loaded {len(messages)} messages from history")
                # Debug: show what messages we loaded
                for i, msg in enumerate(messages):
                    msg_type = "USER" if isinstance(msg, HumanMessage) else "BOT"
                    preview = msg.content[:80].replace('\n', ' ')
                    logger.debug(f"  [{i}] {msg_type}: {preview}...")

            # Add current user message if not already in history
            if not messages or messages[-1].content != user_message:
                messages.append(HumanMessage(content=user_message))
                logger.debug(f"  [+] Added current message: {user_message[:80]}...")

            logger.info(f"📤 Sending {len(messages)} total messages to agent")

            # Process with orchestrator agent (with full history)
            response = self.agent.agent.invoke(
                {"messages": messages},
                config={"configurable": {"thread_id": conversation_id}}
            )

            # Extract bot response from agent output
            if isinstance(response, dict) and "messages" in response:
                last_message = response["messages"][-1]
                if hasattr(last_message, 'content'):
                    bot_response = str(last_message.content)
                else:
                    bot_response = str(last_message)
            else:
                bot_response = str(response)

            logger.info(f"🤖 Generated response (length: {len(bot_response)} chars)")

            # Write bot response to database
            if supabase_db_client.is_available():
                supabase_db_client.insert_message(
                    conversation_id=conversation_id,
                    content=bot_response,
                    user_id=user_id,
                    role='assistant',  # Bot writes as 'assistant' (won't trigger listener)
                    metadata=record.get('metadata')
                )
                logger.success(f"✅ Response sent for conversation: {conversation_id}")
            else:
                logger.error("Supabase DB client unavailable - cannot write response")

        except Exception as e:
            logger.error(f"Error handling message: {e}")
            # Optionally: Write error message to chat
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
