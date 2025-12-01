"""
Database module for Eneca AI Bot

Provides Supabase client for chat_messages table operations.
"""

from database.supabase_client import supabase_db_client

__all__ = ['supabase_db_client']
