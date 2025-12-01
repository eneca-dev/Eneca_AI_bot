"""
Test RAG with correct environment (removing SIMILARITY_THRESHOLD override)
"""
import sys
import os

# Remove environment override BEFORE importing settings
if 'SIMILARITY_THRESHOLD' in os.environ:
    print(f"WARNING: Found SIMILARITY_THRESHOLD={os.environ['SIMILARITY_THRESHOLD']} in environment")
    print("Removing it to use .env value...")
    del os.environ['SIMILARITY_THRESHOLD']

from loguru import logger
from agents.orchestrator import OrchestratorAgent
from core.config import settings

# Setup minimal logging
logger.remove()
logger.add(sys.stderr, level="INFO")

print(f"\n{'='*60}")
print(f"CONFIGURATION CHECK:")
print(f"{'='*60}")
print(f"Loaded SIMILARITY_THRESHOLD: {settings.similarity_threshold}")
print(f"Expected from .env: 0.35")
print(f"{'='*60}\n")

# Test question
test_question = "Где найти раздел планирования и как его первоначально настроить?"

print(f"Testing RAG with question: {test_question}\n")

# Initialize agent
agent = OrchestratorAgent()

# Process message
response = agent.process_message(
    user_message=test_question,
    thread_id="test_thread"
)

print(f"\n{'='*60}")
print("BOT RESPONSE:")
print(f"{'='*60}")
print(response)
print(f"{'='*60}\n")
