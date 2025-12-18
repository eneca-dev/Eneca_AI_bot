"""
Debug script to check messages in Supabase chat_messages table
"""
import sys
import os
# Fix Windows console encoding
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, '.')

from database.supabase_client import supabase_db_client
from loguru import logger

def check_recent_messages(conversation_id: str = None, limit: int = 10):
    """Check recent messages in chat_messages table"""

    if not supabase_db_client.is_available():
        print("❌ Supabase client not available")
        return

    try:
        query = supabase_db_client.client.table("chat_messages")\
            .select("id, conversation_id, user_id, role, content, created_at")\
            .order("created_at", desc=True)\
            .limit(limit)

        if conversation_id:
            query = query.eq("conversation_id", conversation_id)

        response = query.execute()

        print(f"\n📋 Last {limit} messages" + (f" for conversation {conversation_id}" if conversation_id else "") + ":\n")
        print("-" * 100)

        for msg in response.data:
            role_emoji = "👤" if msg['role'] == 'user' else "🤖"
            content_preview = msg['content'][:80] + "..." if len(msg['content']) > 80 else msg['content']
            print(f"{role_emoji} [{msg['role']:10}] {msg['created_at'][:19]}")
            print(f"   conversation: {msg['conversation_id']}")
            print(f"   user_id: {msg['user_id']}")
            print(f"   content: {content_preview}")
            print("-" * 100)

    except Exception as e:
        print(f"❌ Error: {e}")

def check_assistant_messages(limit: int = 5):
    """Check only assistant messages"""

    if not supabase_db_client.is_available():
        print("❌ Supabase client not available")
        return

    try:
        response = supabase_db_client.client.table("chat_messages")\
            .select("id, conversation_id, user_id, role, content, kind, is_final, created_at")\
            .eq("role", "assistant")\
            .order("created_at", desc=True)\
            .limit(limit)\
            .execute()

        print(f"\n🤖 Last {limit} ASSISTANT messages:\n")
        print("-" * 100)

        for msg in response.data:
            content_preview = msg['content'][:100] + "..." if len(msg['content']) > 100 else msg['content']
            print(f"🤖 [{msg['created_at'][:19]}]")
            print(f"   id: {msg['id']}")
            print(f"   conversation: {msg['conversation_id']}")
            print(f"   user_id: {msg['user_id']}")
            print(f"   kind: {msg.get('kind')}, is_final: {msg.get('is_final')}")
            print(f"   content: {content_preview}")
            print("-" * 100)

    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Check messages in Supabase")
    parser.add_argument("--conversation", "-c", help="Filter by conversation_id")
    parser.add_argument("--limit", "-l", type=int, default=10, help="Number of messages to show")
    parser.add_argument("--assistant", "-a", action="store_true", help="Show only assistant messages")

    args = parser.parse_args()

    if args.assistant:
        check_assistant_messages(args.limit)
    else:
        check_recent_messages(args.conversation, args.limit)
