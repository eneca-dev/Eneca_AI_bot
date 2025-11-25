"""
Encoding Migration Script for Supabase Documents

This script fixes encoding issues in documents stored in Supabase.
Supports multiple encoding detection and conversion strategies.

Usage:
    # Dry run (preview only)
    python scripts/fix_encoding_migration.py

    # Execute migration with backup
    python scripts/fix_encoding_migration.py --execute

    # Execute without backup (dangerous!)
    python scripts/fix_encoding_migration.py --execute --no-backup
"""

import sys
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import argparse

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import settings
from core.vector_store import vector_store_manager
from loguru import logger


class EncodingFixer:
    """Handles detection and fixing of encoding issues in documents"""

    ENCODING_STRATEGIES = [
        ('latin1', 'utf-8'),      # Common web encoding issue
        ('cp1251', 'utf-8'),      # Windows Cyrillic → UTF-8
        ('windows-1251', 'utf-8'), # Alternative name
        ('iso-8859-5', 'utf-8'),  # ISO Cyrillic → UTF-8
    ]

    @staticmethod
    def detect_and_fix(text: str) -> Tuple[str, Optional[str]]:
        """
        Try to detect and fix encoding issues in text

        Args:
            text: Text with potential encoding issues

        Returns:
            Tuple of (fixed_text, strategy_used)
            If no fix needed, returns (original_text, None)
        """
        # Check if text is already valid UTF-8 with Russian chars
        try:
            # If we can encode/decode without errors and have Cyrillic, it's likely OK
            text.encode('utf-8').decode('utf-8')
            if any(ord(c) > 1000 for c in text):  # Has Cyrillic range chars
                return text, None
        except (UnicodeDecodeError, UnicodeEncodeError):
            pass

        # Try each encoding strategy
        for from_enc, to_enc in EncodingFixer.ENCODING_STRATEGIES:
            try:
                # Attempt to fix by encoding as from_enc, then decoding as to_enc
                fixed = text.encode(from_enc).decode(to_enc)

                # Validate: should have Cyrillic characters
                if any(ord(c) >= 0x0400 and ord(c) <= 0x04FF for c in fixed):
                    strategy = f"{from_enc}→{to_enc}"
                    logger.debug(f"Fixed encoding using strategy: {strategy}")
                    return fixed, strategy
            except (UnicodeDecodeError, UnicodeEncodeError, AttributeError):
                continue

        # No fix worked, return original
        logger.warning(f"Could not fix encoding for text: {text[:50]}...")
        return text, None

    @staticmethod
    def preview_fix(original: str, fixed: str, max_len: int = 100) -> str:
        """Generate a preview comparison of original vs fixed text"""
        return f"""
Original: {original[:max_len]}{'...' if len(original) > max_len else ''}
Fixed:    {fixed[:max_len]}{'...' if len(fixed) > max_len else ''}
"""


class DocumentMigrator:
    """Handles document export, fixing, and re-upload to Supabase"""

    def __init__(self, dry_run: bool = True, create_backup: bool = True):
        """
        Initialize migrator

        Args:
            dry_run: If True, only preview changes without executing
            create_backup: If True, create JSON backup before migration
        """
        self.dry_run = dry_run
        self.create_backup = create_backup
        self.backup_path: Optional[Path] = None

        # Check if vector store is available
        if not vector_store_manager.is_available():
            raise RuntimeError(
                "Supabase vector store не доступен. "
                "Проверьте SUPABASE_URL и SUPABASE_KEY в .env"
            )

        self.supabase = vector_store_manager.supabase_client

    def export_documents(self) -> List[Dict[str, Any]]:
        """
        Export all documents from Supabase

        Returns:
            List of document dictionaries with id, content, metadata, embedding
        """
        logger.info("Экспорт документов из Supabase...")

        try:
            response = self.supabase.table("documents").select("*").execute()
            documents = response.data
            logger.info(f"Экспортировано {len(documents)} документов")
            return documents
        except Exception as e:
            logger.error(f"Ошибка при экспорте документов: {e}")
            raise

    def create_backup_file(self, documents: List[Dict[str, Any]]) -> Path:
        """
        Create JSON backup of documents

        Args:
            documents: List of documents to backup

        Returns:
            Path to backup file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = Path(__file__).parent.parent / "data" / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        backup_file = backup_dir / f"documents_backup_{timestamp}.json"

        logger.info(f"Создание backup файла: {backup_file}")

        # Convert embeddings for JSON serialization
        serializable_docs = []
        for doc in documents:
            doc_copy = doc.copy()
            if 'embedding' in doc_copy and doc_copy['embedding']:
                # Truncate embedding for smaller backup size
                embedding = doc_copy['embedding']
                if isinstance(embedding, (list, tuple)):
                    # If it's already a list, keep first 10 dimensions
                    doc_copy['embedding'] = list(embedding[:10]) + ['...truncated']
                elif isinstance(embedding, str):
                    # If it's a string (JSON), just mark as truncated
                    doc_copy['embedding'] = '[...truncated for backup size]'
                else:
                    # Remove embedding entirely if unknown type
                    doc_copy['embedding'] = None
            serializable_docs.append(doc_copy)

        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(serializable_docs, f, ensure_ascii=False, indent=2)

        logger.info(f"Backup сохранён: {backup_file}")
        return backup_file

    def analyze_documents(self, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze documents and detect encoding issues

        Args:
            documents: List of documents to analyze

        Returns:
            Analysis report dictionary
        """
        logger.info("Анализ документов на проблемы с кодировкой...")

        total = len(documents)
        needs_fix = 0
        fix_strategies = {}
        previews = []

        for doc in documents:
            content = doc.get('content', '')
            if not content:
                continue

            fixed_content, strategy = EncodingFixer.detect_and_fix(content)

            if strategy:  # Fix was applied
                needs_fix += 1
                fix_strategies[strategy] = fix_strategies.get(strategy, 0) + 1

                # Store preview for first 5 documents that need fixing
                if len(previews) < 5:
                    previews.append({
                        'id': doc['id'],
                        'preview': EncodingFixer.preview_fix(content, fixed_content),
                        'strategy': strategy
                    })

        report = {
            'total_documents': total,
            'needs_fix': needs_fix,
            'ok': total - needs_fix,
            'fix_strategies_used': fix_strategies,
            'sample_previews': previews
        }

        return report

    def fix_documents(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Fix encoding in all documents

        Args:
            documents: List of documents with potential encoding issues

        Returns:
            List of documents with fixed encoding
        """
        logger.info("Исправление кодировки в документах...")

        fixed_documents = []
        stats = {'fixed': 0, 'unchanged': 0, 'errors': 0}

        for doc in documents:
            try:
                content = doc.get('content', '')
                if not content:
                    fixed_documents.append(doc)
                    stats['unchanged'] += 1
                    continue

                fixed_content, strategy = EncodingFixer.detect_and_fix(content)

                if strategy:
                    stats['fixed'] += 1
                    logger.debug(f"Doc {doc['id']}: {strategy}")
                else:
                    stats['unchanged'] += 1

                # Create new document dict with fixed content
                fixed_doc = doc.copy()
                fixed_doc['content'] = fixed_content
                fixed_documents.append(fixed_doc)

            except Exception as e:
                logger.error(f"Ошибка при обработке документа {doc.get('id')}: {e}")
                stats['errors'] += 1
                fixed_documents.append(doc)  # Keep original on error

        logger.info(
            f"Исправлено: {stats['fixed']}, "
            f"Без изменений: {stats['unchanged']}, "
            f"Ошибок: {stats['errors']}"
        )

        return fixed_documents

    def clear_documents_table(self) -> None:
        """Clear all documents from Supabase table (dangerous!)"""
        logger.warning("⚠️  УДАЛЕНИЕ всех документов из таблицы...")

        try:
            # Delete all rows (PostgreSQL doesn't support delete().eq('id', 0))
            # We need to delete in batches or use RPC
            response = self.supabase.table("documents").delete().neq('id', -1).execute()
            logger.info("Таблица documents очищена")
        except Exception as e:
            logger.error(f"Ошибка при очистке таблицы: {e}")
            raise

    def upload_documents(self, documents: List[Dict[str, Any]]) -> None:
        """
        Upload fixed documents back to Supabase

        Args:
            documents: List of documents with fixed encoding
        """
        logger.info(f"Загрузка {len(documents)} документов в Supabase...")

        texts = [doc['content'] for doc in documents]
        metadatas = [doc.get('metadata', {}) for doc in documents]

        try:
            # Use vector_store_manager to add documents
            # This will regenerate embeddings with correct text
            vector_store_manager.add_documents(texts=texts, metadatas=metadatas)
            logger.info("✅ Документы успешно загружены")
        except Exception as e:
            logger.error(f"Ошибка при загрузке документов: {e}")
            raise

    def migrate(self) -> None:
        """Execute full migration pipeline"""
        logger.info("=" * 60)
        logger.info("МИГРАЦИЯ КОДИРОВКИ ДОКУМЕНТОВ")
        logger.info(f"Режим: {'DRY RUN (preview only)' if self.dry_run else 'EXECUTE'}")
        logger.info(f"Backup: {'Enabled' if self.create_backup else 'Disabled'}")
        logger.info("=" * 60)

        # Step 1: Export
        documents = self.export_documents()
        if not documents:
            logger.warning("Нет документов для миграции")
            return

        # Step 2: Backup (if enabled)
        if self.create_backup:
            self.backup_path = self.create_backup_file(documents)

        # Step 3: Analyze
        report = self.analyze_documents(documents)

        logger.info("\n" + "=" * 60)
        logger.info("РЕЗУЛЬТАТЫ АНАЛИЗА")
        logger.info("=" * 60)
        logger.info(f"Всего документов: {report['total_documents']}")
        logger.info(f"Требуют исправления: {report['needs_fix']}")
        logger.info(f"В порядке: {report['ok']}")

        if report['fix_strategies_used']:
            logger.info("\nИспользованные стратегии:")
            for strategy, count in report['fix_strategies_used'].items():
                logger.info(f"  {strategy}: {count} документов")

        if report['sample_previews']:
            logger.info("\nПримеры исправлений:")
            for preview in report['sample_previews']:
                logger.info(f"\nДокумент ID: {preview['id']} (стратегия: {preview['strategy']})")
                logger.info(preview['preview'])

        # Step 4: Fix documents
        if report['needs_fix'] == 0:
            logger.info("\n✅ Все документы в корректной кодировке. Миграция не требуется.")
            return

        fixed_documents = self.fix_documents(documents)

        # Step 5: Upload (if not dry run)
        if not self.dry_run:
            logger.info("\n" + "=" * 60)
            logger.info("ВЫПОЛНЕНИЕ МИГРАЦИИ")
            logger.info("=" * 60)

            # Confirm before proceeding
            logger.warning("⚠️  ВНИМАНИЕ: Сейчас будут удалены все документы и загружены исправленные!")
            logger.warning(f"⚠️  Backup сохранён в: {self.backup_path}")

            try:
                self.clear_documents_table()
                self.upload_documents(fixed_documents)

                logger.info("\n" + "=" * 60)
                logger.info("✅ МИГРАЦИЯ УСПЕШНО ЗАВЕРШЕНА")
                logger.info("=" * 60)
                logger.info(f"Исправлено документов: {report['needs_fix']}")
                logger.info(f"Backup файл: {self.backup_path}")
                logger.info("\nТеперь можно повысить similarity_threshold до 0.7 в .env")

            except Exception as e:
                logger.error("\n" + "=" * 60)
                logger.error("❌ ОШИБКА ПРИ МИГРАЦИИ")
                logger.error("=" * 60)
                logger.error(f"Ошибка: {e}")
                logger.error(f"Backup файл для восстановления: {self.backup_path}")
                raise
        else:
            logger.info("\n" + "=" * 60)
            logger.info("DRY RUN MODE - изменения не применены")
            logger.info("=" * 60)
            logger.info("Для выполнения миграции запустите с флагом --execute:")
            logger.info("python scripts/fix_encoding_migration.py --execute")


def main():
    """Main entry point for the script"""
    parser = argparse.ArgumentParser(
        description='Fix encoding issues in Supabase documents'
    )
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Execute migration (default is dry-run preview only)'
    )
    parser.add_argument(
        '--no-backup',
        action='store_true',
        help='Skip backup creation (dangerous!)'
    )

    args = parser.parse_args()

    # Configure logger
    logger.remove()  # Remove default handler
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO"
    )

    try:
        migrator = DocumentMigrator(
            dry_run=not args.execute,
            create_backup=not args.no_backup
        )
        migrator.migrate()

    except KeyboardInterrupt:
        logger.warning("\n❌ Миграция прервана пользователем")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"❌ Критическая ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
