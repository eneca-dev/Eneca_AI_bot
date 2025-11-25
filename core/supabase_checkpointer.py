"""
Custom Supabase Checkpointer for LangGraph using n8n_chat_histories table

This module provides a checkpointer implementation that stores conversation
history in Supabase PostgreSQL using the existing n8n_chat_histories table.
"""

import json
from typing import Optional, Dict, Any, Iterator, Tuple
from datetime import datetime
from langgraph.checkpoint.base import BaseCheckpointSaver, Checkpoint, CheckpointMetadata
from supabase import Client
from loguru import logger


class SupabaseCheckpointer(BaseCheckpointSaver):
    """
    Checkpointer that stores conversation history in Supabase n8n_chat_histories table

    Expected table schema (n8n_chat_histories):
    - id: bigint (primary key)
    - session_id: text (maps to thread_id)
    - message_type: text ('ai' or 'human')
    - message: text (JSON serialized checkpoint data)
    - created_at: timestamp
    - metadata: jsonb (optional)
    """

    def __init__(
        self,
        supabase_client: Client,
        table_name: str = "n8n_chat_histories"
    ):
        """
        Initialize Supabase checkpointer

        Args:
            supabase_client: Supabase client instance
            table_name: Name of the table to store checkpoints (default: n8n_chat_histories)
        """
        super().__init__()
        self.client = supabase_client
        self.table_name = table_name
        logger.info(f"SupabaseCheckpointer initialized with table: {table_name}")

    def put(
        self,
        config: Dict[str, Any],
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata
    ) -> Dict[str, Any]:
        """
        Save a checkpoint to Supabase

        Args:
            config: Configuration dict containing thread_id
            checkpoint: Checkpoint data to save
            metadata: Checkpoint metadata

        Returns:
            Updated config dict
        """
        thread_id = config.get("configurable", {}).get("thread_id")
        if not thread_id:
            raise ValueError("thread_id is required in config.configurable")

        try:
            # Serialize checkpoint and metadata
            checkpoint_data = {
                "checkpoint": self._serialize_checkpoint(checkpoint),
                "metadata": metadata
            }

            # Insert into n8n_chat_histories table
            data = {
                "session_id": thread_id,
                "message_type": "checkpoint",  # Use special type for checkpoints
                "message": json.dumps(checkpoint_data, ensure_ascii=False),
                "created_at": datetime.utcnow().isoformat(),
                "metadata": metadata  # Store metadata separately for querying
            }

            response = self.client.table(self.table_name).insert(data).execute()

            logger.debug(f"Checkpoint saved for thread_id: {thread_id}")
            return config

        except Exception as e:
            logger.error(f"Error saving checkpoint to Supabase: {e}")
            raise

    def get(
        self,
        config: Dict[str, Any]
    ) -> Optional[Tuple[Checkpoint, CheckpointMetadata]]:
        """
        Retrieve the latest checkpoint for a thread

        Args:
            config: Configuration dict containing thread_id

        Returns:
            Tuple of (checkpoint, metadata) or None if not found
        """
        thread_id = config.get("configurable", {}).get("thread_id")
        if not thread_id:
            return None

        try:
            # Query latest checkpoint for this session
            response = self.client.table(self.table_name)\
                .select("*")\
                .eq("session_id", thread_id)\
                .eq("message_type", "checkpoint")\
                .order("created_at", desc=True)\
                .limit(1)\
                .execute()

            if not response.data:
                logger.debug(f"No checkpoint found for thread_id: {thread_id}")
                return None

            # Deserialize checkpoint data
            latest = response.data[0]
            checkpoint_data = json.loads(latest["message"])

            checkpoint = self._deserialize_checkpoint(checkpoint_data["checkpoint"])
            metadata = checkpoint_data.get("metadata", {})

            logger.debug(f"Checkpoint retrieved for thread_id: {thread_id}")
            return checkpoint, metadata

        except Exception as e:
            logger.error(f"Error retrieving checkpoint from Supabase: {e}")
            return None

    def list(
        self,
        config: Dict[str, Any],
        limit: int = 10
    ) -> Iterator[Tuple[Checkpoint, CheckpointMetadata]]:
        """
        List checkpoints for a thread

        Args:
            config: Configuration dict containing thread_id
            limit: Maximum number of checkpoints to return

        Yields:
            Tuples of (checkpoint, metadata)
        """
        thread_id = config.get("configurable", {}).get("thread_id")
        if not thread_id:
            return

        try:
            # Query checkpoints for this session
            response = self.client.table(self.table_name)\
                .select("*")\
                .eq("session_id", thread_id)\
                .eq("message_type", "checkpoint")\
                .order("created_at", desc=True)\
                .limit(limit)\
                .execute()

            for row in response.data:
                try:
                    checkpoint_data = json.loads(row["message"])
                    checkpoint = self._deserialize_checkpoint(checkpoint_data["checkpoint"])
                    metadata = checkpoint_data.get("metadata", {})
                    yield checkpoint, metadata
                except Exception as e:
                    logger.warning(f"Error deserializing checkpoint: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error listing checkpoints from Supabase: {e}")

    def _serialize_checkpoint(self, checkpoint: Checkpoint) -> Dict[str, Any]:
        """
        Serialize checkpoint to JSON-compatible dict

        Args:
            checkpoint: Checkpoint to serialize

        Returns:
            JSON-serializable dict
        """
        # Convert checkpoint to dict representation
        # LangGraph checkpoints contain messages and state
        return {
            "v": 1,  # Version
            "data": checkpoint  # Store entire checkpoint
        }

    def _deserialize_checkpoint(self, data: Dict[str, Any]) -> Checkpoint:
        """
        Deserialize checkpoint from dict

        Args:
            data: Serialized checkpoint data

        Returns:
            Checkpoint object
        """
        version = data.get("v", 1)
        if version == 1:
            return data.get("data", {})
        else:
            raise ValueError(f"Unsupported checkpoint version: {version}")

    def delete_thread(self, thread_id: str) -> bool:
        """
        Delete all checkpoints for a thread

        Args:
            thread_id: Thread ID to delete

        Returns:
            True if successful, False otherwise
        """
        try:
            response = self.client.table(self.table_name)\
                .delete()\
                .eq("session_id", thread_id)\
                .eq("message_type", "checkpoint")\
                .execute()

            logger.info(f"Deleted checkpoints for thread_id: {thread_id}")
            return True

        except Exception as e:
            logger.error(f"Error deleting thread from Supabase: {e}")
            return False

    def get_conversation_history(
        self,
        thread_id: str,
        limit: int = 50
    ) -> list:
        """
        Get full conversation history including user/AI messages

        Args:
            thread_id: Thread ID (session_id)
            limit: Maximum number of messages to retrieve

        Returns:
            List of messages with type and content
        """
        try:
            response = self.client.table(self.table_name)\
                .select("*")\
                .eq("session_id", thread_id)\
                .order("created_at", desc=False)\
                .limit(limit)\
                .execute()

            messages = []
            for row in response.data:
                # Skip checkpoint entries
                if row["message_type"] == "checkpoint":
                    continue

                messages.append({
                    "type": row["message_type"],
                    "content": row["message"],
                    "created_at": row["created_at"],
                    "metadata": row.get("metadata", {})
                })

            logger.debug(f"Retrieved {len(messages)} messages for thread_id: {thread_id}")
            return messages

        except Exception as e:
            logger.error(f"Error getting conversation history: {e}")
            return []
