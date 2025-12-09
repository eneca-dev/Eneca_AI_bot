-- Migration: Add missing columns to n8n_chat_histories table
-- This migration is safe and backward-compatible with n8n workflows

-- Add message_type column (stores 'human', 'ai', 'checkpoint')
-- For existing records, extract type from message JSONB
ALTER TABLE n8n_chat_histories
ADD COLUMN IF NOT EXISTS message_type TEXT;

-- Add metadata column for additional checkpoint data
ALTER TABLE n8n_chat_histories
ADD COLUMN IF NOT EXISTS metadata JSONB;

-- Add created_at timestamp for better ordering
ALTER TABLE n8n_chat_histories
ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();

-- Update existing records: extract message_type from message JSON
-- Only if message_type is NULL (new column)
UPDATE n8n_chat_histories
SET message_type = message->>'type'
WHERE message_type IS NULL
  AND message ? 'type';

-- Backfill created_at for existing records (use current timestamp as fallback)
UPDATE n8n_chat_histories
SET created_at = NOW()
WHERE created_at IS NULL;

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_chat_histories_session_id
ON n8n_chat_histories(session_id);

CREATE INDEX IF NOT EXISTS idx_chat_histories_created_at
ON n8n_chat_histories(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_chat_histories_message_type
ON n8n_chat_histories(message_type);

CREATE INDEX IF NOT EXISTS idx_chat_histories_session_created
ON n8n_chat_histories(session_id, created_at DESC);

-- Verify migration
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'n8n_chat_histories'
ORDER BY ordinal_position;
