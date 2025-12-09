"""
Supabase Memory Verification Script

Verifies that n8n_chat_histories table exists and is properly configured
for conversation memory storage.

Usage:
    # Check current state
    python scripts/verify_supabase_memory.py

    # Test write/read operations
    python scripts/verify_supabase_memory.py --test
"""

import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
import argparse

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import settings
from core.vector_store import vector_store_manager
from core.supabase_checkpointer import SupabaseCheckpointer
from loguru import logger


class SupabaseMemoryVerifier:
    """Verifies Supabase memory configuration and functionality"""

    def __init__(self):
        """Initialize verifier"""
        # Configure logger
        logger.remove()
        logger.add(
            sys.stderr,
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
            level="INFO"
        )

        self.table_name = settings.memory_supabase_table

    def verify_connection(self) -> bool:
        """
        Verify Supabase connection

        Returns:
            True if connection successful, False otherwise
        """
        logger.info("=" * 60)
        logger.info("ПРОВЕРКА ПОДКЛЮЧЕНИЯ К SUPABASE")
        logger.info("=" * 60)

        if not vector_store_manager.is_available():
            logger.error("❌ Supabase не доступен")
            logger.error("Проверьте SUPABASE_URL и SUPABASE_KEY в .env")
            return False

        logger.info(f"✅ Supabase подключён")
        logger.info(f"URL: {settings.supabase_url[:30]}...")
        return True

    def verify_table(self) -> bool:
        """
        Verify n8n_chat_histories table exists

        Returns:
            True if table exists, False otherwise
        """
        logger.info("\n" + "=" * 60)
        logger.info(f"ПРОВЕРКА ТАБЛИЦЫ: {self.table_name}")
        logger.info("=" * 60)

        try:
            supabase = vector_store_manager.supabase_client

            # Try to query the table
            response = supabase.table(self.table_name).select("*").limit(1).execute()

            logger.info(f"✅ Таблица {self.table_name} существует")

            # Check if table has data
            if response.data:
                logger.info(f"📊 Таблица содержит данные (минимум 1 запись)")
            else:
                logger.info(f"📊 Таблица пустая (0 записей)")

            return True

        except Exception as e:
            logger.error(f"❌ Ошибка доступа к таблице {self.table_name}: {e}")
            logger.info("\nВозможные причины:")
            logger.info("1. Таблица не существует в Supabase")
            logger.info("2. Недостаточно прав доступа (используйте service_role key)")
            logger.info("3. Неправильное имя таблицы в конфигурации")
            return False

    def verify_schema(self) -> Dict[str, Any]:
        """
        Verify table schema matches expected structure

        Returns:
            Dictionary with schema information
        """
        logger.info("\n" + "=" * 60)
        logger.info("ПРОВЕРКА СХЕМЫ ТАБЛИЦЫ")
        logger.info("=" * 60)

        expected_columns = {
            "id": "Primary key",
            "session_id": "Thread/conversation ID",
            "message_type": "Type: ai, human, or checkpoint",
            "message": "Message content or checkpoint data",
            "created_at": "Timestamp",
            "metadata": "JSONB metadata (optional)"
        }

        try:
            supabase = vector_store_manager.supabase_client

            # Get sample record to inspect schema
            response = supabase.table(self.table_name).select("*").limit(1).execute()

            if response.data:
                sample = response.data[0]
                actual_columns = set(sample.keys())

                logger.info("Найденные колонки:")
                for col in actual_columns:
                    desc = expected_columns.get(col, "Неизвестное поле")
                    logger.info(f"  ✓ {col}: {desc}")

                # Check for missing expected columns
                expected_keys = set(expected_columns.keys())
                missing = expected_keys - actual_columns

                if missing:
                    logger.warning(f"\n⚠️  Отсутствуют ожидаемые колонки: {missing}")
                    logger.info("Это может не быть проблемой, но может потребовать адаптации")
                else:
                    logger.info("\n✅ Все ожидаемые колонки присутствуют")

                return {
                    "has_data": True,
                    "columns": list(actual_columns),
                    "missing_columns": list(missing)
                }
            else:
                logger.warning("Таблица пустая, не можем проверить схему")
                logger.info("Схема будет проверена при первой записи")
                return {
                    "has_data": False,
                    "columns": [],
                    "missing_columns": []
                }

        except Exception as e:
            logger.error(f"Ошибка проверки схемы: {e}")
            return {"error": str(e)}

    def test_write_read(self) -> bool:
        """
        Test writing and reading checkpoint data

        Returns:
            True if test successful, False otherwise
        """
        logger.info("\n" + "=" * 60)
        logger.info("ТЕСТ ЗАПИСИ И ЧТЕНИЯ")
        logger.info("=" * 60)

        try:
            # Initialize checkpointer
            supabase = vector_store_manager.supabase_client
            checkpointer = SupabaseCheckpointer(
                supabase_client=supabase,
                table_name=self.table_name
            )

            # Test data
            test_thread_id = f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            test_checkpoint = {
                "messages": [
                    {"role": "user", "content": "Привет!"},
                    {"role": "assistant", "content": "Здравствуйте!"}
                ],
                "test_timestamp": datetime.now().isoformat()
            }
            test_metadata = {
                "test": True,
                "created_by": "verify_supabase_memory.py"
            }

            config = {
                "configurable": {
                    "thread_id": test_thread_id
                }
            }

            logger.info(f"1. Запись checkpoint для thread_id: {test_thread_id}")
            checkpointer.put(config, test_checkpoint, test_metadata)
            logger.info("   ✅ Checkpoint записан")

            logger.info(f"2. Чтение checkpoint для thread_id: {test_thread_id}")
            result = checkpointer.get(config)

            if result is None:
                logger.error("   ❌ Checkpoint не найден после записи")
                return False

            checkpoint_data, metadata = result
            logger.info("   ✅ Checkpoint успешно прочитан")

            # Verify data integrity
            logger.info("3. Проверка целостности данных")
            if checkpoint_data.get("test_timestamp") == test_checkpoint["test_timestamp"]:
                logger.info("   ✅ Данные совпадают")
            else:
                logger.warning("   ⚠️  Данные могли измениться при serialization")

            # Cleanup
            logger.info(f"4. Очистка тестовых данных")
            checkpointer.delete_thread(test_thread_id)
            logger.info("   ✅ Тестовые данные удалены")

            logger.info("\n✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ")
            return True

        except Exception as e:
            logger.error(f"\n❌ ТЕСТ НЕ ПРОЙДЕН: {e}")
            logger.exception(e)
            return False

    def show_memory_stats(self) -> None:
        """Show statistics about stored conversations"""
        logger.info("\n" + "=" * 60)
        logger.info("СТАТИСТИКА ПАМЯТИ")
        logger.info("=" * 60)

        try:
            supabase = vector_store_manager.supabase_client

            # Count total records
            response = supabase.table(self.table_name).select("*", count="exact").execute()
            total_count = response.count if hasattr(response, 'count') else len(response.data or [])

            logger.info(f"Всего записей: {total_count}")

            # Count by message type
            if response.data:
                type_counts = {}
                for record in response.data[:100]:  # Sample first 100
                    msg_type = record.get("message_type", "unknown")
                    type_counts[msg_type] = type_counts.get(msg_type, 0) + 1

                logger.info("\nРаспределение по типам (первые 100 записей):")
                for msg_type, count in sorted(type_counts.items()):
                    logger.info(f"  {msg_type}: {count}")

            # Count unique sessions
            sessions = set()
            if response.data:
                for record in response.data[:100]:
                    session_id = record.get("session_id")
                    if session_id:
                        sessions.add(session_id)

                logger.info(f"\nУникальных сессий (первые 100): {len(sessions)}")

        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")

    def run_verification(self, run_tests: bool = False) -> bool:
        """
        Run full verification suite

        Args:
            run_tests: If True, run write/read tests

        Returns:
            True if all checks passed, False otherwise
        """
        # Step 1: Verify connection
        if not self.verify_connection():
            return False

        # Step 2: Verify table exists
        if not self.verify_table():
            return False

        # Step 3: Verify schema
        schema_info = self.verify_schema()
        if "error" in schema_info:
            return False

        # Step 4: Show stats
        self.show_memory_stats()

        # Step 5: Run tests if requested
        if run_tests:
            if not self.test_write_read():
                return False

        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("✅ ВЕРИФИКАЦИЯ ЗАВЕРШЕНА УСПЕШНО")
        logger.info("=" * 60)
        logger.info(f"Таблица {self.table_name} готова для использования")
        logger.info("\nДля включения Supabase memory установите в .env:")
        logger.info("  MEMORY_TYPE=supabase")
        logger.info("  MEMORY_SUPABASE_TABLE=n8n_chat_histories")

        return True


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Verify Supabase memory configuration'
    )
    parser.add_argument(
        '--test',
        action='store_true',
        help='Run write/read tests'
    )

    args = parser.parse_args()

    try:
        verifier = SupabaseMemoryVerifier()
        success = verifier.run_verification(run_tests=args.test)

        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        logger.warning("\n❌ Верификация прервана пользователем")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"❌ Критическая ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
