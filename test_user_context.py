"""Test script for user profile context integration"""
from agents.orchestrator import OrchestratorAgent
from loguru import logger
import sys

# Configure logger for console output
logger.remove()
logger.add(sys.stderr, level="INFO")

def test_user_context():
    """Test user context integration"""

    logger.info("=" * 60)
    logger.info("User Context Integration Test")
    logger.info("=" * 60)

    # Initialize orchestrator
    logger.info("\n1. Initializing OrchestratorAgent...")
    orchestrator = OrchestratorAgent()

    # Test 1: Without user context
    logger.info("\n2. Test WITHOUT user context:")
    response1 = orchestrator.process_message(
        "Привет!",
        thread_id="test_no_context"
    )
    logger.info(f"   Response: {response1}\n")

    # Test 2: With mock user context
    logger.info("3. Test WITH user context:")
    mock_user_context = {
        'first_name': 'Александра',
        'last_name': 'Бирило',
        'job_title': 'Главный инженер',
        'department': 'Инженерный отдел',
        'email': 'a.birilo@eneca.ru'
    }

    response2 = orchestrator.process_message(
        "Привет!",
        thread_id="test_with_context",
        user_context=mock_user_context
    )
    logger.info(f"   Response: {response2}\n")

    # Test 3: Verify formatted context
    logger.info("4. Test context formatting:")
    formatted = orchestrator._format_user_context(mock_user_context)
    logger.info(f"   Formatted context:\n{formatted}\n")

    # Test 4: Partial user context
    logger.info("5. Test with partial context (only name):")
    partial_context = {
        'first_name': 'Иван',
        'last_name': 'Петров'
    }

    response3 = orchestrator.process_message(
        "Как дела?",
        thread_id="test_partial_context",
        user_context=partial_context
    )
    logger.info(f"   Response: {response3}\n")

    # Test 5: Empty context
    logger.info("6. Test with empty context:")
    empty_context = {}
    formatted_empty = orchestrator._format_user_context(empty_context)
    logger.info(f"   Empty context formatted: '{formatted_empty}' (should be empty)")

    logger.info("\n" + "=" * 60)
    logger.info("User Context Integration Test Completed")
    logger.info("=" * 60)

if __name__ == "__main__":
    test_user_context()
