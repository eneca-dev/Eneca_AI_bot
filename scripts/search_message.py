"""
Search for specific message content in chat_messages
"""
import sys
import os
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, '.')

from database.supabase_client import supabase_db_client

def search_messages(search_text: str):
    """Search for messages containing text"""
    if not supabase_db_client.is_available():
        print("Supabase client not available")
        return

    try:
        # Search using ilike for case-insensitive partial match
        response = supabase_db_client.client.table("chat_messages")\
            .select("id, conversation_id, user_id, role, content, created_at")\
            .ilike("content", f"%{search_text}%")\
            .order("created_at", desc=True)\
            .limit(10)\
            .execute()

        print(f"\nSearch results for '{search_text}':\n")
        print("-" * 100)

        if not response.data:
            print("No messages found")
            return

        for msg in response.data:
            role_emoji = "User" if msg['role'] == 'user' else "Bot"
            print(f"[{role_emoji}] {msg['created_at'][:19]}")
            print(f"   conversation: {msg['conversation_id']}")
            print(f"   content: {msg['content'][:150]}")
            print("-" * 100)

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("text", help="Text to search for")
    args = parser.parse_args()
    search_messages(args.text)
