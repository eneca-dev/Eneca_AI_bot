"""
Simple test script for RAG functionality
"""
import sys
from loguru import logger
from agents.orchestrator import OrchestratorAgent

# Setup minimal logging
logger.remove()
logger.add(sys.stderr, level="INFO")

# Test question
test_question = "Где найти раздел планирования и как его первоначально настроить?"

print(f"\nTesting RAG with question: {test_question}\n")

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
