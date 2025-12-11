"""Test script to fetch real user profile from Supabase"""
from database.supabase_client import supabase_db_client
from agents.orchestrator import OrchestratorAgent
from loguru import logger
import sys

# Configure logger for console output
logger.remove()
logger.add(sys.stderr, level="INFO")

def test_real_profile():
    """Test fetching real user profile and using it with orchestrator"""

    user_id = "003006e8-9859-4462-989d-1a3787189d7a"

    logger.info("=" * 60)
    logger.info(f"Testing Real User Profile: {user_id}")
    logger.info("=" * 60)

    # Step 1: Fetch profile from Supabase
    logger.info("\n1. Fetching user profile from Supabase...")
    if not supabase_db_client.is_available():
        logger.error("   ❌ Supabase DB Client not available!")
        return

    user_context = supabase_db_client.get_user_profile(user_id)

    if user_context:
        logger.info("   ✅ Profile loaded successfully!")
        logger.info(f"   📋 Profile data:")
        for key, value in user_context.items():
            logger.info(f"      - {key}: {value}")
    else:
        logger.warning("   ⚠️ No profile found for this user_id")
        logger.info("   Proceeding without context...")

    # Step 2: Initialize orchestrator
    logger.info("\n2. Initializing OrchestratorAgent...")
    orchestrator = OrchestratorAgent()

    # Step 3: Format context
    if user_context:
        logger.info("\n3. Formatting user context:")
        formatted = orchestrator._format_user_context(user_context)
        logger.info(f"   {formatted}")

    # Step 4: Test with real profile
    logger.info("\n4. Testing message with real profile context:")
    response = orchestrator.process_message(
        "Привет! Как дела?",
        thread_id=f"test_{user_id}",
        user_context=user_context
    )
    logger.info(f"   Bot response: {response}")

    # Step 5: Test another message
    logger.info("\n5. Testing project-related query:")
    response2 = orchestrator.process_message(
        "Покажи мои проекты",
        thread_id=f"test_{user_id}",
        user_context=user_context
    )
    logger.info(f"   Bot response: {response2}")

    logger.info("\n" + "=" * 60)
    logger.info("Real Profile Test Completed")
    logger.info("=" * 60)

if __name__ == "__main__":
    test_real_profile()