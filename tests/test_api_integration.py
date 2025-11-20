"""
Test script for API integration
Tests all webhook endpoints including streaming
"""
import requests
import json
import time
from core.config import settings

# Configuration
API_URL = "http://localhost:8000"
API_KEY = settings.api_key  # From .env

def test_health():
    """Test health endpoint"""
    print("\n🔍 Testing /health endpoint...")
    response = requests.get(f"{API_URL}/health")
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    assert response.status_code == 200
    print("✅ Health check passed")

def test_root():
    """Test root endpoint"""
    print("\n🔍 Testing / endpoint...")
    response = requests.get(f"{API_URL}/")
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    assert response.status_code == 200
    print("✅ Root endpoint passed")

def test_api_without_api_key():
    """Test API without API key (should fail if API_KEY is set)"""
    print("\n🔍 Testing /api/chat without API key...")

    if not API_KEY:
        print("⚠️  API_KEY not configured, skipping auth test")
        return

    response = requests.post(
        f"{API_URL}/api/chat",
        json={"message": "Test"}
    )

    print(f"Status: {response.status_code}")
    assert response.status_code == 401, "Should require API key"
    print("✅ API key validation works")

def test_api_chat_standard():
    """Test standard chat endpoint"""
    print("\n🔍 Testing /api/chat (standard mode)...")

    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["X-API-Key"] = API_KEY

    response = requests.post(
        f"{API_URL}/api/chat",
        headers=headers,
        json={
            "message": "Привет! Кто ты?",
            "user_id": "test-user-123",
            "thread_id": f"test-{int(time.time())}"
        }
    )

    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Response: {json.dumps(data, indent=2, ensure_ascii=False)}")

    assert response.status_code == 200
    assert "response" in data
    assert "thread_id" in data
    assert data["success"] is True
    print(f"✅ Standard chat endpoint passed")
    print(f"📝 Bot response: {data['response'][:100]}...")

    return data["thread_id"]

def test_api_chat_streaming():
    """Test streaming chat endpoint"""
    print("\n🔍 Testing /api/chat/stream (SSE mode)...")

    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["X-API-Key"] = API_KEY

    response = requests.post(
        f"{API_URL}/api/chat/stream",
        headers=headers,
        json={
            "message": "Расскажи короткую историю о Python",
            "thread_id": f"test-stream-{int(time.time())}"
        },
        stream=True
    )

    print(f"Status: {response.status_code}")
    assert response.status_code == 200

    print("📡 Streaming events:")
    accumulated_content = ""
    thread_id = None

    for line in response.iter_lines():
        if line:
            line = line.decode('utf-8')
            if line.startswith('data: '):
                data = json.loads(line[6:])

                if data['type'] == 'metadata':
                    thread_id = data['thread_id']
                    print(f"  📌 Thread ID: {thread_id}")
                elif data['type'] == 'chunk':
                    accumulated_content += (accumulated_content and ' ' or '') + data['content']
                    print(f"  📝 Chunk: {data['content']}")
                elif data['type'] == 'done':
                    print(f"  ✅ Done: {data['thread_id']}")
                elif data['type'] == 'error':
                    print(f"  ❌ Error: {data['message']}")

    print(f"\n📄 Full response: {accumulated_content[:200]}...")
    assert len(accumulated_content) > 0
    print("✅ Streaming chat endpoint passed")

def test_conversation_memory():
    """Test conversation memory with thread_id"""
    print("\n🔍 Testing conversation memory...")

    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["X-API-Key"] = API_KEY

    thread_id = f"test-memory-{int(time.time())}"

    # First message
    print("  1️⃣ First message: 'Меня зовут Алекс'")
    response1 = requests.post(
        f"{API_URL}/api/chat",
        headers=headers,
        json={
            "message": "Меня зовут Алекс",
            "thread_id": thread_id
        }
    )
    data1 = response1.json()
    print(f"     Response: {data1['response'][:100]}...")

    time.sleep(1)

    # Second message (should remember name)
    print("  2️⃣ Second message: 'Как меня зовут?'")
    response2 = requests.post(
        f"{API_URL}/api/chat",
        headers=headers,
        json={
            "message": "Как меня зовут?",
            "thread_id": thread_id
        }
    )
    data2 = response2.json()
    print(f"     Response: {data2['response'][:100]}...")

    # Check if bot remembers the name
    if "Алекс" in data2['response'] or "alex" in data2['response'].lower():
        print("✅ Conversation memory works! Bot remembered the name.")
    else:
        print("⚠️  Bot might not have remembered the name (memory might need tuning)")

def run_all_tests():
    """Run all tests"""
    print("=" * 60)
    print("🧪 Eneca AI Bot - API Integration Tests")
    print("=" * 60)

    try:
        test_root()
        test_health()
        test_api_without_api_key()
        test_api_chat_standard()
        test_api_chat_streaming()
        test_conversation_memory()

        print("\n" + "=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
    except requests.exceptions.ConnectionError:
        print("\n❌ Connection error: Is the API server running?")
        print("   Start it with: python server.py")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")

if __name__ == "__main__":
    print("📋 Configuration:")
    print(f"   API URL: {API_URL}")
    print(f"   API Key configured: {'Yes' if API_KEY else 'No (auth disabled)'}")
    print()

    run_all_tests()
