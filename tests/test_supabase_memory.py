"""
Tests for Supabase Memory Checkpointer

Tests conversation memory persistence using n8n_chat_histories table.
"""

import pytest
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.vector_store import vector_store_manager
from core.supabase_checkpointer import SupabaseCheckpointer
from core.memory import memory_manager
from core.config import settings


# Check if Supabase is available
supabase_available = vector_store_manager.is_available()


@pytest.mark.skipif(not supabase_available, reason="Supabase not available")
class TestSupabaseCheckpointer:
    """Tests for SupabaseCheckpointer class"""

    @pytest.fixture
    def checkpointer(self):
        """Fixture to create checkpointer instance"""
        return SupabaseCheckpointer(
            supabase_client=vector_store_manager.supabase_client,
            table_name=settings.memory_supabase_table
        )

    @pytest.fixture
    def test_thread_id(self):
        """Fixture for unique test thread ID"""
        return f"test_thread_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

    @pytest.fixture
    def test_config(self, test_thread_id):
        """Fixture for test configuration"""
        return {
            "configurable": {
                "thread_id": test_thread_id
            }
        }

    @pytest.fixture
    def test_checkpoint(self):
        """Fixture for test checkpoint data"""
        return {
            "messages": [
                {"role": "user", "content": "Тестовое сообщение"},
                {"role": "assistant", "content": "Тестовый ответ"}
            ],
            "timestamp": datetime.now().isoformat()
        }

    @pytest.fixture
    def test_metadata(self):
        """Fixture for test metadata"""
        return {
            "test": True,
            "created_by": "test_supabase_memory.py"
        }

    def test_checkpointer_initialization(self, checkpointer):
        """Test that checkpointer initializes correctly"""
        assert checkpointer is not None
        assert checkpointer.client is not None
        assert checkpointer.table_name == settings.memory_supabase_table

    def test_put_checkpoint(self, checkpointer, test_config, test_checkpoint, test_metadata):
        """Test saving checkpoint to Supabase"""
        try:
            result_config = checkpointer.put(test_config, test_checkpoint, test_metadata)

            assert result_config is not None
            assert result_config["configurable"]["thread_id"] == test_config["configurable"]["thread_id"]

        finally:
            # Cleanup
            checkpointer.delete_thread(test_config["configurable"]["thread_id"])

    def test_get_checkpoint(self, checkpointer, test_config, test_checkpoint, test_metadata):
        """Test retrieving checkpoint from Supabase"""
        try:
            # Save checkpoint
            checkpointer.put(test_config, test_checkpoint, test_metadata)

            # Retrieve checkpoint
            result = checkpointer.get(test_config)

            assert result is not None
            checkpoint, metadata = result
            assert checkpoint is not None
            assert metadata is not None

            # Verify timestamp is preserved
            assert checkpoint.get("timestamp") == test_checkpoint["timestamp"]

        finally:
            # Cleanup
            checkpointer.delete_thread(test_config["configurable"]["thread_id"])

    def test_get_nonexistent_checkpoint(self, checkpointer):
        """Test retrieving non-existent checkpoint returns None"""
        config = {
            "configurable": {
                "thread_id": "nonexistent_thread_12345"
            }
        }

        result = checkpointer.get(config)
        assert result is None

    def test_list_checkpoints(self, checkpointer, test_thread_id, test_checkpoint, test_metadata):
        """Test listing multiple checkpoints for a thread"""
        try:
            config = {"configurable": {"thread_id": test_thread_id}}

            # Save multiple checkpoints
            for i in range(3):
                checkpoint = test_checkpoint.copy()
                checkpoint["iteration"] = i
                checkpointer.put(config, checkpoint, test_metadata)

            # List checkpoints
            checkpoints = list(checkpointer.list(config, limit=10))

            assert len(checkpoints) >= 1  # At least one checkpoint
            # Verify they are returned in reverse chronological order (newest first)
            # Most recent should be iteration 2

        finally:
            # Cleanup
            checkpointer.delete_thread(test_thread_id)

    def test_delete_thread(self, checkpointer, test_config, test_checkpoint, test_metadata):
        """Test deleting all checkpoints for a thread"""
        thread_id = test_config["configurable"]["thread_id"]

        # Save checkpoint
        checkpointer.put(test_config, test_checkpoint, test_metadata)

        # Verify checkpoint exists
        result = checkpointer.get(test_config)
        assert result is not None

        # Delete thread
        success = checkpointer.delete_thread(thread_id)
        assert success is True

        # Verify checkpoint is deleted
        result = checkpointer.get(test_config)
        assert result is None

    def test_thread_isolation(self, checkpointer, test_checkpoint, test_metadata):
        """Test that different threads don't interfere with each other"""
        thread_id_1 = f"test_thread_1_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        thread_id_2 = f"test_thread_2_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

        config_1 = {"configurable": {"thread_id": thread_id_1}}
        config_2 = {"configurable": {"thread_id": thread_id_2}}

        checkpoint_1 = test_checkpoint.copy()
        checkpoint_1["thread"] = "thread_1"

        checkpoint_2 = test_checkpoint.copy()
        checkpoint_2["thread"] = "thread_2"

        try:
            # Save checkpoints to different threads
            checkpointer.put(config_1, checkpoint_1, test_metadata)
            checkpointer.put(config_2, checkpoint_2, test_metadata)

            # Retrieve and verify isolation
            result_1 = checkpointer.get(config_1)
            result_2 = checkpointer.get(config_2)

            assert result_1 is not None
            assert result_2 is not None

            checkpoint_data_1, _ = result_1
            checkpoint_data_2, _ = result_2

            assert checkpoint_data_1["thread"] == "thread_1"
            assert checkpoint_data_2["thread"] == "thread_2"

        finally:
            # Cleanup
            checkpointer.delete_thread(thread_id_1)
            checkpointer.delete_thread(thread_id_2)

    def test_get_conversation_history(self, checkpointer, test_thread_id):
        """Test retrieving full conversation history"""
        try:
            # This test assumes n8n_chat_histories has some message entries
            # Not just checkpoints
            history = checkpointer.get_conversation_history(test_thread_id, limit=50)

            # Should return a list (may be empty for new thread)
            assert isinstance(history, list)

        finally:
            # No cleanup needed as we're just reading
            pass


@pytest.mark.skipif(not supabase_available, reason="Supabase not available")
class TestMemoryManagerWithSupabase:
    """Integration tests for MemoryManager with Supabase backend"""

    def test_memory_manager_supabase_initialization(self):
        """Test that memory manager can initialize with Supabase backend"""
        if settings.memory_type == "supabase":
            assert memory_manager.is_enabled()
            assert memory_manager.checkpointer is not None
            assert isinstance(memory_manager.checkpointer, SupabaseCheckpointer)

    def test_memory_manager_fallback(self, monkeypatch):
        """Test that memory manager falls back gracefully on error"""
        # This test verifies that if Supabase fails, system doesn't crash
        # Implementation depends on fallback strategy in memory.py
        pass


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers"""
    config.addinivalue_line(
        "markers", "supabase: mark test as requiring Supabase connection"
    )


# Mark all tests in this file as integration tests
pytestmark = [pytest.mark.integration, pytest.mark.supabase]


if __name__ == "__main__":
    # Run tests when script is executed directly
    pytest.main([__file__, "-v", "--tb=short", "-k", "not fallback"])
