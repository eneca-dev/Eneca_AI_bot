#!/bin/bash

# Test script for Supabase webhook endpoint
# Usage: bash test_webhook.sh

echo "=== Testing Supabase Webhook Endpoint ==="
echo ""

# Test 1: Valid user message
echo "[Test 1] Sending valid user message..."
curl -X POST http://localhost:8000/webhook/supabase \
  -H "Content-Type: application/json" \
  -d '{
    "type": "INSERT",
    "table": "chat_messages",
    "schema": "public",
    "record": {
      "id": "test-123",
      "user_id": "test_user",
      "thread_id": "test_thread_1",
      "role": "user",
      "content": "Что такое Eneca?",
      "metadata": {}
    }
  }'

echo ""
echo ""

# Test 2: Assistant message (should be ignored)
echo "[Test 2] Sending assistant message (should be ignored)..."
curl -X POST http://localhost:8000/webhook/supabase \
  -H "Content-Type: application/json" \
  -d '{
    "type": "INSERT",
    "table": "chat_messages",
    "schema": "public",
    "record": {
      "id": "test-456",
      "user_id": "test_user",
      "thread_id": "test_thread_2",
      "role": "assistant",
      "content": "Это ответ бота",
      "metadata": {}
    }
  }'

echo ""
echo ""
echo "=== Tests Complete ==="
echo "Check logs/app.log for background processing status"
