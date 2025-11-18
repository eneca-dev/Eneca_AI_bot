"""Test script for Orchestrator with RAG routing"""
from agents.orchestrator import OrchestratorAgent

print("=" * 80)
print("Testing Eneca AI Bot - Orchestrator + RAG Agent")
print("=" * 80)

# Initialize orchestrator agent
print("\n[Initializing] OrchestratorAgent with RAG tool...")
agent = OrchestratorAgent()
print("[OK] Agent initialized successfully\n")

# Test messages - mix of simple questions and RAG-requiring questions
test_messages = [
    {
        "message": "Привет! Как дела?",
        "description": "Simple greeting (should answer without tool)",
        "category": "Simple"
    },
    {
        "message": "Что такое Python?",
        "description": "General knowledge (should answer without tool)",
        "category": "General"
    },
    {
        "message": "Как создать новый проект в Eneca?",
        "description": "Specific app question (should use knowledge_search tool)",
        "category": "RAG"
    },
    {
        "message": "Где находится раздел настроек?",
        "description": "App navigation question (should use knowledge_search tool)",
        "category": "RAG"
    },
    {
        "message": "Спасибо за помощь!",
        "description": "Simple acknowledgment (should answer without tool)",
        "category": "Simple"
    }
]

print("=" * 80)
print("Running Tests")
print("=" * 80)

for i, test in enumerate(test_messages, 1):
    message = test["message"]
    description = test["description"]
    category = test["category"]

    print(f"\n[Test {i}/{len(test_messages)}] {category} Query")
    print(f"Description: {description}")
    print(f"User: {message}")
    print("-" * 80)

    try:
        response = agent.process_message(message)
        print(f"Bot: {response}")
        print(f"[OK] Test {i} completed\n")
    except Exception as e:
        print(f"[ERROR] Test {i} failed: {e}\n")

    print("=" * 80)

print("\nAll tests completed!")
print("\nNote: RAG tool will show 'База знаний временно недоступна'")
print("until Supabase credentials are provided in .env file.")
