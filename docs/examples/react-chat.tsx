/**
 * React Chat Component Example for Eneca AI Bot
 *
 * Features:
 * - API Key authentication
 * - Streaming responses (SSE)
 * - Conversation memory (thread_id)
 * - TypeScript support
 */

import React, { useState, useRef, useEffect } from 'react';

// Types
interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

interface ChatProps {
  apiUrl: string;  // e.g., "http://localhost:8000" or "https://your-domain.com"
  apiKey?: string; // Optional API key
  threadId?: string; // Optional thread ID for conversation continuity
  userId?: string;   // Optional user ID
}

const EnecaChat: React.FC<ChatProps> = ({
  apiUrl,
  apiKey,
  threadId: initialThreadId,
  userId
}) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [threadId, setThreadId] = useState(initialThreadId || '');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  /**
   * Send message with streaming response
   */
  const sendMessageStreaming = async (message: string) => {
    if (!message.trim()) return;

    // Add user message to chat
    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: message,
      timestamp: new Date()
    };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    // Create placeholder for assistant message
    const assistantMessageId = (Date.now() + 1).toString();
    const assistantMessage: Message = {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date()
    };
    setMessages(prev => [...prev, assistantMessage]);

    try {
      // Prepare request
      const headers: HeadersInit = {
        'Content-Type': 'application/json',
      };
      if (apiKey) {
        headers['X-API-Key'] = apiKey;
      }

      const response = await fetch(`${apiUrl}/api/chat/stream`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          message,
          thread_id: threadId,
          user_id: userId
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      // Read streaming response
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        throw new Error('No response body');
      }

      let accumulatedContent = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        // Decode chunk
        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = JSON.parse(line.slice(6));

            if (data.type === 'metadata') {
              // Save thread_id for conversation continuity
              setThreadId(data.thread_id);
            } else if (data.type === 'chunk') {
              // Append content chunk
              accumulatedContent += (accumulatedContent ? ' ' : '') + data.content;

              // Update assistant message
              setMessages(prev => prev.map(msg =>
                msg.id === assistantMessageId
                  ? { ...msg, content: accumulatedContent }
                  : msg
              ));
            } else if (data.type === 'error') {
              console.error('Streaming error:', data.message);
              throw new Error(data.message);
            }
          }
        }
      }

    } catch (error) {
      console.error('Error sending message:', error);

      // Update assistant message with error
      setMessages(prev => prev.map(msg =>
        msg.id === assistantMessageId
          ? { ...msg, content: 'Произошла ошибка при обработке запроса. Попробуйте еще раз.' }
          : msg
      ));
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Send message with standard (non-streaming) response
   */
  const sendMessageStandard = async (message: string) => {
    if (!message.trim()) return;

    // Add user message
    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: message,
      timestamp: new Date()
    };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      // Prepare request
      const headers: HeadersInit = {
        'Content-Type': 'application/json',
      };
      if (apiKey) {
        headers['X-API-Key'] = apiKey;
      }

      const response = await fetch(`${apiUrl}/api/chat`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          message,
          thread_id: threadId,
          user_id: userId
        })
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Request failed');
      }

      // Save thread_id
      setThreadId(data.thread_id);

      // Add assistant response
      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: data.response,
        timestamp: new Date()
      };
      setMessages(prev => [...prev, assistantMessage]);

    } catch (error) {
      console.error('Error sending message:', error);

      // Add error message
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: 'Произошла ошибка при обработке запроса. Попробуйте еще раз.',
        timestamp: new Date()
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    // Choose streaming or standard mode
    sendMessageStreaming(input);
    // Or use: sendMessageStandard(input);
  };

  return (
    <div className="chat-container" style={{
      display: 'flex',
      flexDirection: 'column',
      height: '600px',
      maxWidth: '800px',
      margin: '0 auto',
      border: '1px solid #ddd',
      borderRadius: '8px'
    }}>
      {/* Messages */}
      <div style={{
        flex: 1,
        overflowY: 'auto',
        padding: '20px',
        backgroundColor: '#f5f5f5'
      }}>
        {messages.map(msg => (
          <div
            key={msg.id}
            style={{
              marginBottom: '16px',
              textAlign: msg.role === 'user' ? 'right' : 'left'
            }}
          >
            <div style={{
              display: 'inline-block',
              padding: '12px 16px',
              borderRadius: '8px',
              backgroundColor: msg.role === 'user' ? '#007bff' : '#fff',
              color: msg.role === 'user' ? '#fff' : '#000',
              maxWidth: '70%',
              textAlign: 'left',
              boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
            }}>
              {msg.content}
            </div>
          </div>
        ))}
        {isLoading && (
          <div style={{ textAlign: 'left', color: '#666' }}>
            <em>AI печатает...</em>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} style={{
        padding: '16px',
        borderTop: '1px solid #ddd',
        backgroundColor: '#fff'
      }}>
        <div style={{ display: 'flex', gap: '8px' }}>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Введите сообщение..."
            disabled={isLoading}
            style={{
              flex: 1,
              padding: '12px',
              border: '1px solid #ddd',
              borderRadius: '4px',
              fontSize: '14px'
            }}
          />
          <button
            type="submit"
            disabled={isLoading || !input.trim()}
            style={{
              padding: '12px 24px',
              backgroundColor: '#007bff',
              color: '#fff',
              border: 'none',
              borderRadius: '4px',
              cursor: isLoading ? 'not-allowed' : 'pointer',
              fontSize: '14px',
              fontWeight: 'bold'
            }}
          >
            Отправить
          </button>
        </div>
      </form>
    </div>
  );
};

export default EnecaChat;

/**
 * Usage Example:
 *
 * import EnecaChat from './EnecaChat';
 *
 * function App() {
 *   return (
 *     <EnecaChat
 *       apiUrl="http://localhost:8000"
 *       apiKey="your-api-key-here"  // Optional
 *       userId="user-123"            // Optional
 *     />
 *   );
 * }
 */
