"""FastAPI webhook server for Eneca AI Bot integration"""
from fastapi import FastAPI, HTTPException, Request, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, AsyncIterator
from agents.orchestrator import OrchestratorAgent
from core.config import settings
from loguru import logger
import uuid
import uvicorn
import json
import asyncio

# Initialize FastAPI app
app = FastAPI(
    title="Eneca AI Bot Webhook",
    description="Webhook endpoint for Eneca AI Bot integration with n8n",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize orchestrator agent (singleton)
agent = None

def get_agent() -> OrchestratorAgent:
    """Get or create orchestrator agent instance"""
    global agent
    if agent is None:
        logger.info("Initializing OrchestratorAgent...")
        agent = OrchestratorAgent()
        logger.info("OrchestratorAgent initialized successfully")
    return agent


async def verify_api_key(x_api_key: str = Header(None, alias=settings.api_key_header)):
    """
    Verify API key from request header

    Args:
        x_api_key: API key from header (header name configured in settings)

    Raises:
        HTTPException: If API key is required but missing or invalid
    """
    # Skip verification if API key is not configured
    if not settings.api_key:
        return None

    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="API key is required. Include it in the request header."
        )

    if x_api_key != settings.api_key:
        logger.warning(f"Invalid API key attempt: {x_api_key[:10]}...")
        raise HTTPException(
            status_code=403,
            detail="Invalid API key"
        )

    return x_api_key


class WebhookRequest(BaseModel):
    """Webhook request model"""
    message: str
    user_id: Optional[str] = None
    chat_id: Optional[str] = None
    thread_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class WebhookResponse(BaseModel):
    """Webhook response model"""
    message: str  # Changed from 'response' to match client expectations
    thread_id: str
    user_id: Optional[str] = None
    chat_id: Optional[str] = None
    success: bool = True
    error: Optional[str] = None


@app.on_event("startup")
async def startup_event():
    """Initialize agent on startup"""
    logger.info("Starting webhook server...")
    get_agent()
    logger.info("Webhook server ready!")


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "ok",
        "service": "Eneca AI Bot Webhook",
        "version": "1.0.0",
        "agent_loaded": agent is not None
    }


@app.get("/health")
async def health():
    """Detailed health check"""
    agent_instance = get_agent()
    return {
        "status": "healthy",
        "agent": {
            "initialized": agent_instance is not None,
            "tools": len(agent_instance.tools) if agent_instance else 0,
            "memory_enabled": agent_instance.checkpointer is not None if agent_instance else False
        }
    }


@app.post("/api/chat", response_model=WebhookResponse)
async def chat_endpoint(
    request: WebhookRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    Main chat endpoint for sending messages to AI bot

    Headers (if API_KEY is configured in .env):
        X-API-Key: your_api_key

    Expected payload:
    {
        "message": "User message text",
        "user_id": "optional-user-id",
        "chat_id": "optional-chat-id",
        "thread_id": "optional-thread-id",
        "metadata": {}
    }

    Returns:
    {
        "message": "Agent response",
        "thread_id": "conversation-thread-id",
        "success": true
    }
    """
    try:
        logger.info(f"Received chat request: {request.model_dump()}")

        # Get agent instance
        agent_instance = get_agent()

        # Generate or use provided thread_id
        thread_id = request.thread_id or request.chat_id or str(uuid.uuid4())

        # Process message with agent
        logger.info(f"Processing message for thread: {thread_id}")
        response = agent_instance.process_message(
            user_message=request.message,
            thread_id=thread_id
        )

        logger.info(f"Agent response generated successfully for thread: {thread_id}")

        # Create response object
        response_obj = WebhookResponse(
            message=response,  # Changed from 'response' to 'message'
            thread_id=thread_id,
            user_id=request.user_id,
            chat_id=request.chat_id,
            success=True
        )

        # Log the exact JSON being returned
        logger.debug(f"Returning response: {response_obj.model_dump_json()}")

        return response_obj

    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error processing message: {str(e)}"
        )


@app.post("/api/chat/stream")
async def chat_stream(
    request: WebhookRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    Streaming chat endpoint with Server-Sent Events (SSE)

    Headers (if API_KEY is configured in .env):
        X-API-Key: your_api_key

    Expected payload:
    {
        "message": "User message text",
        "thread_id": "optional-thread-id"
    }

    Returns:
        Server-Sent Events stream with agent response chunks
    """
    async def event_generator() -> AsyncIterator[str]:
        """Generate Server-Sent Events for streaming response"""
        try:
            # Get agent instance
            agent_instance = get_agent()

            # Generate or use provided thread_id
            thread_id = request.thread_id or request.chat_id or str(uuid.uuid4())

            logger.info(f"Starting streaming response for thread: {thread_id}")

            # Send metadata event
            yield f"data: {json.dumps({'type': 'metadata', 'thread_id': thread_id})}\n\n"

            # Process message in executor (non-blocking)
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                agent_instance.process_message,
                request.message,
                thread_id
            )

            # Simulate streaming by breaking response into chunks
            # TODO: Replace with real streaming when LangChain streaming is implemented
            chunk_size = 20  # characters per chunk
            words = response.split()
            current_chunk = []
            current_length = 0

            for word in words:
                current_chunk.append(word)
                current_length += len(word) + 1  # +1 for space

                if current_length >= chunk_size:
                    chunk_text = " ".join(current_chunk)
                    yield f"data: {json.dumps({'type': 'chunk', 'content': chunk_text})}\n\n"
                    current_chunk = []
                    current_length = 0
                    await asyncio.sleep(0.05)  # Small delay for smoother streaming

            # Send remaining chunk
            if current_chunk:
                chunk_text = " ".join(current_chunk)
                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk_text})}\n\n"

            # Send completion event
            yield f"data: {json.dumps({'type': 'done', 'thread_id': thread_id})}\n\n"

            logger.info(f"Streaming completed for thread: {thread_id}")

        except Exception as e:
            logger.error(f"Error in streaming: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


@app.post("/api/debug")
async def debug_endpoint(request: Request):
    """
    Debug endpoint for testing
    Accepts any JSON and logs it
    """
    try:
        data = await request.json()
        logger.info(f"Raw webhook data: {data}")

        # Try to extract message
        message = data.get("message") or data.get("text") or data.get("query")

        if not message:
            return {
                "error": "No message found in request",
                "received_data": data,
                "hint": "Send JSON with 'message', 'text', or 'query' field"
            }

        # Process with agent
        agent_instance = get_agent()
        thread_id = data.get("thread_id") or data.get("chat_id") or str(uuid.uuid4())

        response = agent_instance.process_message(
            user_message=message,
            thread_id=thread_id
        )

        return {
            "success": True,
            "response": response,
            "thread_id": thread_id,
            "received_data": data
        }

    except Exception as e:
        logger.error(f"Error in raw webhook: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


if __name__ == "__main__":
    # Run server
    logger.info("Starting Eneca AI Bot webhook server on http://localhost:8000")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
