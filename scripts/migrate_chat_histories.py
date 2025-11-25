"""
Migrate n8n_chat_histories table to add missing columns

Adds message_type, metadata, and created_at columns to support
LangGraph checkpointer while maintaining n8n compatibility.

Usage:
    # Dry run (show what will be done)
    python scripts/migrate_chat_histories.py

    # Execute migration
    python scripts/migrate_chat_histories.py --execute
"""

import sys
from pathlib import Path
import argparse

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.vector_store import vector_store_manager
from loguru import logger


class ChatHistoriesMigration:
    """Migrates n8n_chat_histories table to add checkpointer columns"""

    def __init__(self):
        """Initialize migration"""
        # Configure logger
        logger.remove()
        logger.add(
            sys.stderr,
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
            level="INFO"
        )

        self.supabase = vector_store_manager.supabase_client

    def check_current_schema(self):
        """Check current table schema"""
        logger.info("=" * 60)
        logger.info("ПРОВЕРКА ТЕКУЩЕЙ СХЕМЫ ТАБЛИЦЫ")
        logger.info("=" * 60)

        # Get current columns
        query = """
            SELECT
                column_name,
                data_type,
                is_nullable
            FROM information_schema.columns
            WHERE table_name = 'n8n_chat_histories'
            ORDER BY ordinal_position;
        """

        try:
            result = self.supabase.rpc('exec_sql', {'query': query}).execute()

            if result.data:
                logger.info("Текущие колонки:")
                for col in result.data:
                    logger.info(f"  - {col['column_name']}: {col['data_type']}")

                # Check for missing columns
                column_names = {col['column_name'] for col in result.data}
                required = {'message_type', 'metadata', 'created_at'}
                missing = required - column_names

                if missing:
                    logger.warning(f"\n⚠️  Отсутствуют колонки: {missing}")
                    return False
                else:
                    logger.info("\n✅ Все необходимые колонки присутствуют")
                    return True
            else:
                # Fallback: query table directly
                sample = self.supabase.table('n8n_chat_histories').select('*').limit(1).execute()
                if sample.data:
                    column_names = set(sample.data[0].keys())
                    logger.info(f"Текущие колонки: {column_names}")

                    required = {'message_type', 'metadata', 'created_at'}
                    missing = required - column_names

                    if missing:
                        logger.warning(f"⚠️  Отсутствуют колонки: {missing}")
                        return False
                    else:
                        logger.info("✅ Все необходимые колонки присутствуют")
                        return True

        except Exception as e:
            logger.error(f"Ошибка проверки схемы: {e}")
            logger.info("Попытка альтернативной проверки...")

            # Fallback: try to query table
            try:
                sample = self.supabase.table('n8n_chat_histories').select('*').limit(1).execute()
                if sample.data:
                    column_names = set(sample.data[0].keys())
                    logger.info(f"Текущие колонки: {column_names}")

                    required = {'message_type', 'metadata', 'created_at'}
                    missing = required - column_names

                    if missing:
                        logger.warning(f"⚠️  Отсутствуют колонки: {missing}")
                        return False
                    else:
                        logger.info("✅ Все необходимые колонки присутствуют")
                        return True
            except Exception as e2:
                logger.error(f"Ошибка альтернативной проверки: {e2}")
                return False

    def show_migration_plan(self):
        """Show what the migration will do"""
        logger.info("\n" + "=" * 60)
        logger.info("ПЛАН МИГРАЦИИ")
        logger.info("=" * 60)

        logger.info("""
Миграция добавит следующие колонки в таблицу n8n_chat_histories:

1. message_type (TEXT)
   - Тип сообщения: 'human', 'ai', 'checkpoint'
   - Будет извлечён из message->>'type' для существующих записей

2. metadata (JSONB)
   - Дополнительные метаданные для checkpoints
   - NULL для существующих записей

3. created_at (TIMESTAMP WITH TIME ZONE)
   - Временная метка создания записи
   - NOW() для существующих записей

Также будут созданы индексы для ускорения поиска:
   - idx_chat_histories_session_id
   - idx_chat_histories_created_at
   - idx_chat_histories_message_type
   - idx_chat_histories_session_created

⚠️  ВАЖНО: Миграция безопасна и не изменит существующие данные.
           Совместимость с n8n workflows сохраняется.
        """)

    def execute_migration(self):
        """Execute the migration"""
        logger.info("\n" + "=" * 60)
        logger.info("ВЫПОЛНЕНИЕ МИГРАЦИИ")
        logger.info("=" * 60)

        # Read SQL migration file
        sql_file = Path(__file__).parent / "migrate_chat_histories_table.sql"

        if not sql_file.exists():
            logger.error(f"SQL файл не найден: {sql_file}")
            return False

        logger.info(f"Чтение SQL миграции из: {sql_file}")

        with open(sql_file, 'r', encoding='utf-8') as f:
            sql_content = f.read()

        # Split by semicolons (each statement)
        statements = [s.strip() for s in sql_content.split(';') if s.strip() and not s.strip().startswith('--')]

        logger.info(f"Найдено {len(statements)} SQL операций")

        try:
            for i, statement in enumerate(statements, 1):
                # Skip comments
                if statement.startswith('--'):
                    continue

                logger.info(f"\n[{i}/{len(statements)}] Выполнение...")
                logger.debug(f"SQL: {statement[:100]}...")

                # Execute via Supabase RPC or direct query
                try:
                    # Try to execute via raw SQL if available
                    result = self.supabase.rpc('exec_sql', {'query': statement}).execute()
                    logger.info(f"✅ Операция {i} выполнена")
                except Exception as e:
                    # Some operations might not be supported via RPC
                    logger.warning(f"⚠️  RPC не поддерживается, выполнение альтернативным методом: {e}")

                    # For ALTER TABLE, we'll need to use Supabase API or psql
                    logger.error("❌ Не удалось выполнить миграцию через Supabase API")
                    logger.info("\nВЫПОЛНИТЕ МИГРАЦИЮ ВРУЧНУЮ через Supabase SQL Editor:")
                    logger.info("1. Откройте Supabase Dashboard → SQL Editor")
                    logger.info(f"2. Скопируйте содержимое файла: {sql_file}")
                    logger.info("3. Вставьте в SQL Editor и нажмите 'Run'")
                    return False

            logger.info("\n✅ МИГРАЦИЯ УСПЕШНО ЗАВЕРШЕНА")
            return True

        except Exception as e:
            logger.error(f"\n❌ ОШИБКА МИГРАЦИИ: {e}")
            logger.exception(e)
            return False

    def verify_migration(self):
        """Verify migration was successful"""
        logger.info("\n" + "=" * 60)
        logger.info("ВЕРИФИКАЦИЯ МИГРАЦИИ")
        logger.info("=" * 60)

        # Check schema again
        schema_ok = self.check_current_schema()

        if schema_ok:
            # Check sample record
            try:
                result = self.supabase.table('n8n_chat_histories').select('*').limit(1).execute()
                if result.data:
                    record = result.data[0]
                    logger.info("\nПример записи после миграции:")
                    logger.info(f"  session_id: {record.get('session_id')}")
                    logger.info(f"  message_type: {record.get('message_type')}")
                    logger.info(f"  created_at: {record.get('created_at')}")
                    logger.info(f"  metadata: {record.get('metadata')}")
                    logger.info("✅ Миграция верифицирована")
                    return True
            except Exception as e:
                logger.error(f"Ошибка верификации: {e}")
                return False
        else:
            logger.error("❌ Верификация не прошла")
            return False

    def run(self, execute: bool = False):
        """Run migration process"""
        # Step 1: Check current schema
        schema_ok = self.check_current_schema()

        if schema_ok:
            logger.info("\n✅ Таблица уже содержит все необходимые колонки. Миграция не требуется.")
            return True

        # Step 2: Show plan
        self.show_migration_plan()

        if not execute:
            logger.info("\n" + "=" * 60)
            logger.info("РЕЖИМ DRY-RUN")
            logger.info("=" * 60)
            logger.info("Это был предварительный просмотр.")
            logger.info("Для выполнения миграции запустите:")
            logger.info("  python scripts/migrate_chat_histories.py --execute")
            logger.info("\nИЛИ выполните миграцию вручную через Supabase SQL Editor:")
            logger.info("  1. Откройте scripts/migrate_chat_histories_table.sql")
            logger.info("  2. Скопируйте SQL код")
            logger.info("  3. Выполните в Supabase Dashboard → SQL Editor")
            return True

        # Step 3: Execute (if --execute flag)
        logger.warning("\n⚠️  ВЫПОЛНЕНИЕ МИГРАЦИИ...")
        logger.info("Нажмите Ctrl+C для отмены или Enter для продолжения")
        try:
            input()
        except KeyboardInterrupt:
            logger.warning("\n❌ Миграция отменена пользователем")
            return False

        # Execute migration
        success = self.execute_migration()

        if success:
            # Verify
            self.verify_migration()
            return True
        else:
            # Manual migration instructions
            logger.info("\n" + "=" * 60)
            logger.info("ИНСТРУКЦИЯ ПО РУЧНОЙ МИГРАЦИИ")
            logger.info("=" * 60)
            sql_file = Path(__file__).parent / "migrate_chat_histories_table.sql"
            logger.info(f"1. Откройте файл: {sql_file}")
            logger.info("2. Скопируйте весь SQL код")
            logger.info("3. Откройте Supabase Dashboard → SQL Editor")
            logger.info("4. Вставьте SQL и нажмите 'Run'")
            logger.info("\nПосле выполнения запустите снова проверку:")
            logger.info("  python scripts/verify_supabase_memory.py")
            return False


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Migrate n8n_chat_histories table for checkpointer support'
    )
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Execute migration (default: dry-run only)'
    )

    args = parser.parse_args()

    try:
        # Check if Supabase is available
        if not vector_store_manager.is_available():
            logger.error("❌ Supabase не доступен. Проверьте .env файл")
            sys.exit(1)

        migration = ChatHistoriesMigration()
        success = migration.run(execute=args.execute)

        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        logger.warning("\n❌ Миграция прервана пользователем")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"❌ Критическая ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
