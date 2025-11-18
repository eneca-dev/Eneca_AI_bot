"""Script to test webhook locally"""
import requests
import json

# Test data
test_message = {
    "message": "Привет! Расскажи что ты умеешь?",
    "user_id": "test_user_123",
    "chat_id": "test_chat_456"
}

print("Testing webhook locally...")
print(f"Sending: {json.dumps(test_message, ensure_ascii=False, indent=2)}\n")

try:
    response = requests.post(
        "http://localhost:8000/webhook",
        json=test_message,
        timeout=60
    )

    print(f"Status: {response.status_code}")
    print(f"Response:\n{json.dumps(response.json(), ensure_ascii=False, indent=2)}")

except requests.exceptions.ConnectionError:
    print("ERROR: Cannot connect to webhook server!")
    print("Make sure the server is running: python webhook_server.py")
except Exception as e:
    print(f"ERROR: {e}")
