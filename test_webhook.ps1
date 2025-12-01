# Test script for Supabase webhook endpoint (PowerShell)
# Usage: .\test_webhook.ps1

Write-Host "=== Testing Supabase Webhook Endpoint ===" -ForegroundColor Green
Write-Host ""

# Test 1: Valid user message
Write-Host "[Test 1] Sending valid user message..." -ForegroundColor Cyan
$body1 = @{
    type = "INSERT"
    table = "chat_messages"
    schema = "public"
    record = @{
        id = "test-123"
        user_id = "test_user"
        thread_id = "test_thread_1"
        role = "user"
        content = "Что такое Eneca?"
        metadata = @{}
    }
} | ConvertTo-Json -Depth 10

$response1 = Invoke-RestMethod -Uri "http://localhost:8000/webhook/supabase" `
    -Method POST `
    -ContentType "application/json" `
    -Body $body1

Write-Host "Response:" -ForegroundColor Yellow
$response1 | ConvertTo-Json
Write-Host ""

# Test 2: Assistant message (should be ignored)
Write-Host "[Test 2] Sending assistant message (should be ignored)..." -ForegroundColor Cyan
$body2 = @{
    type = "INSERT"
    table = "chat_messages"
    schema = "public"
    record = @{
        id = "test-456"
        user_id = "test_user"
        thread_id = "test_thread_2"
        role = "assistant"
        content = "Это ответ бота"
        metadata = @{}
    }
} | ConvertTo-Json -Depth 10

$response2 = Invoke-RestMethod -Uri "http://localhost:8000/webhook/supabase" `
    -Method POST `
    -ContentType "application/json" `
    -Body $body2

Write-Host "Response:" -ForegroundColor Yellow
$response2 | ConvertTo-Json
Write-Host ""

Write-Host "=== Tests Complete ===" -ForegroundColor Green
Write-Host "Check logs/app.log for background processing status" -ForegroundColor Yellow
