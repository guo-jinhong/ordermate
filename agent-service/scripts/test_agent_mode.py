#!/usr/bin/env python3
"""Test the agent health endpoint and chat endpoint."""
import urllib.request
import json

base_url = "http://localhost:18000"

# Test health
print("=== Health Check ===")
try:
    req = urllib.request.Request(f"{base_url}/health")
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read())
        print(json.dumps(data, indent=2, ensure_ascii=False))
        mode = data.get("agent_mode", "unknown")
        print(f"\nAgent mode: {mode}")
        if mode == "demo":
            print("⚠️  Running in DEMO mode - NO DeepSeek calls!")
        elif mode == "live":
            print("✅ Running in LIVE mode - should call DeepSeek")
except Exception as e:
    print(f"Error: {e}")

# Test chat
print("\n=== Chat Test ===")
try:
    # First login
    login_data = json.dumps({"username": "testuser", "password": "password"}).encode()
    login_req = urllib.request.Request(
        f"{base_url}/auth/login",
        data=login_data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(login_req, timeout=5) as resp:
        login_result = json.loads(resp.read())
        token = login_result.get("access_token", "")
        print(f"Login OK, token: {token[:20]}...")

    # Send a chat message
    chat_data = json.dumps({
        "message": "你好",
        "session_id": "test-session-001"
    }).encode()
    chat_req = urllib.request.Request(
        f"{base_url}/chat",
        data=chat_data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        },
        method="POST"
    )
    with urllib.request.urlopen(chat_req, timeout=30) as resp:
        chat_result = json.loads(resp.read())
        print(f"Response: {chat_result.get('answer', 'NO ANSWER')[:200]}")
        print(f"Tool calls: {len(chat_result.get('tool_calls', []))}")
except urllib.error.HTTPError as e:
    print(f"HTTP Error {e.code}: {e.read().decode()[:300]}")
except Exception as e:
    print(f"Error: {e}")
