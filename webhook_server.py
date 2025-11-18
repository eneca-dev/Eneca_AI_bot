"""FastAPI webhook server for Eneca AI Bot integration"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any
from agents.orchestrator import OrchestratorAgent
from loguru import logger
import uuid
import uvicorn

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


class WebhookRequest(BaseModel):
    """Webhook request model"""
    message: str
    user_id: Optional[str] = None
    chat_id: Optional[str] = None
    thread_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class WebhookResponse(BaseModel):
    """Webhook response model"""
    response: str
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


@app.post("/webhook", response_model=WebhookResponse)
async def webhook_endpoint(request: WebhookRequest):
    """
    Main webhook endpoint for receiving messages from n8n

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
        "response": "Agent response",
        "thread_id": "conversation-thread-id",
        "success": true
    }
    """
    try:
        logger.info(f"Received webhook request: {request.model_dump()}")

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

        return WebhookResponse(
            response=response,
            thread_id=thread_id,
            user_id=request.user_id,
            chat_id=request.chat_id,
            success=True
        )

    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error processing message: {str(e)}"
        )


@app.post("/webhook/raw")
async def webhook_raw(request: Request):
    """
    Raw webhook endpoint for debugging
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
