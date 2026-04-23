"""FastAPI webhook server for Eneca AI Bot integration"""
from fastapi import FastAPI, HTTPException, Request, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from pathlib import Path
from typing import Optional, Dict, Any, AsyncIterator
from agents.orchestrator import OrchestratorAgent
from agents.analytics_agent import AnalyticsAgent, AnalyticsResult
from agents.teams_agent import (
    TeamsAgent, MeetingTranscript, MeetingReport,
    MeetingParticipant, TranscriptSegment, Author,
)
from services.teams_sender import teams_sender, format_report_as_text
from services.recall_client import recall_client
from services.whisper_transcriber import whisper_transcriber
from core.config import settings
from loguru import logger
import uuid
import uvicorn
import json
import asyncio
import re

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

# Initialize agents (singletons)
agent = None
analytics_agent = None
teams_agent = None

def get_agent() -> OrchestratorAgent:
    """Get or create orchestrator agent instance"""
    global agent
    if agent is None:
        logger.info("Initializing OrchestratorAgent...")
        agent = OrchestratorAgent()
        logger.info("OrchestratorAgent initialized successfully")
    return agent


def get_analytics_agent() -> AnalyticsAgent:
    """Get or create analytics agent instance"""
    global analytics_agent
    if analytics_agent is None:
        logger.info("Initializing AnalyticsAgent...")
        analytics_agent = AnalyticsAgent()
        logger.info("AnalyticsAgent initialized successfully")
    return analytics_agent


def get_teams_agent() -> TeamsAgent:
    """Get or create teams agent instance"""
    global teams_agent
    if teams_agent is None:
        logger.info("Initializing TeamsAgent...")
        teams_agent = TeamsAgent()
        logger.info("TeamsAgent initialized successfully")
    return teams_agent


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


class AnalyticsRequest(BaseModel):
    """Analytics request model"""
    query: str
    user_id: Optional[str] = None
    user_role: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class AnalyticsResponse(BaseModel):
    """Analytics response model"""
    type: str  # "text", "table", "chart", "mixed"
    content: Any  # String, list, or dict depending on type
    sql_query: Optional[str] = None
    chart_config: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = {}
    success: bool = True
    error: Optional[str] = None


class TeamsProcessRequest(BaseModel):
    """Teams meeting processing request"""
    meeting: MeetingTranscript
    user_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    send_to_teams: bool = True
    teams_conversation_id: Optional[str] = None


class TeamsProcessResponse(BaseModel):
    """Teams meeting processing response"""
    report: Optional[MeetingReport] = None
    success: bool = True
    error: Optional[str] = None
    metadata: Dict[str, Any] = {}


# --- Meeting link detection ---

MEETING_URL_PATTERNS = [
    # Teams meeting links
    re.compile(r'https?://teams\.microsoft\.com/l/meetup-join/[^\s<>"]+', re.IGNORECASE),
    re.compile(r'https?://teams\.microsoft\.com/meet/[^\s<>"]+', re.IGNORECASE),
    re.compile(r'https?://teams\.live\.com/meet/[^\s<>"]+', re.IGNORECASE),
    # Zoom meeting links
    re.compile(r'https?://[\w.-]*zoom\.us/[jw]/[^\s<>"]+', re.IGNORECASE),
    # Google Meet links
    re.compile(r'https?://meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}[^\s<>"]*', re.IGNORECASE),
]


def _build_author_from_conversation(conversation_id: Optional[str]) -> Optional[Author]:
    """Build a protocol Author from the stored Teams conversation reference.

    Returns None when no conversation is known; callers fall back to DEFAULT_AUTHOR.
    Organization and role are not provided by Teams/Bot Framework without extra
    Graph API calls, so they stay empty in this iteration.
    """
    if not conversation_id:
        return None
    ref = teams_sender.get_conversation_reference(conversation_id)
    if not ref:
        return None
    user_name = ref.get("user_name")
    if not user_name:
        return None
    return Author(organization=None, name=user_name, role=None)


def extract_meeting_url(text: str) -> Optional[str]:
    """
    Extract a meeting URL from message text.
    Teams may send links wrapped in HTML <a href="..."> tags.
    Returns the first matching meeting link or None.
    """
    if not text:
        return None

    # Also extract URLs from HTML href attributes (Teams wraps links in <a> tags)
    href_urls = re.findall(r'href=["\']([^"\']+)["\']', text)
    search_text = text + " " + " ".join(href_urls)

    for pattern in MEETING_URL_PATTERNS:
        match = pattern.search(search_text)
        if match:
            return match.group(0).rstrip('.,;:!?)')
    return None


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
        from database.supabase_client import supabase_db_client

        logger.info(f"Received chat request: {request.model_dump()}")

        # Get agent instance
        agent_instance = get_agent()

        # Generate or use provided thread_id
        thread_id = request.thread_id or request.chat_id or str(uuid.uuid4())

        # Load user profile with role (RBAC integration)
        user_context = None
        if request.user_id:
            if supabase_db_client.is_available():
                user_context = supabase_db_client.get_user_profile(request.user_id)
                if user_context:
                    logger.info(f"Loaded user profile: {request.user_id}, role: {user_context.get('role_name')}")
                else:
                    # Profile not found, use guest role
                    logger.warning(f"No profile found for user_id={request.user_id}, using guest role")
                    user_context = {'role_name': 'guest'}
            else:
                # Supabase not available, use guest role
                logger.warning("Supabase not available, using guest role")
                user_context = {'role_name': 'guest'}
        else:
            # No user_id provided, use guest role
            logger.info("No user_id provided, using guest role")
            user_context = {'role_name': 'guest'}

        # Process message with agent (with user context for RBAC)
        logger.info(f"Processing message for thread: {thread_id}, role: {user_context.get('role_name')}")
        response = agent_instance.process_message(
            user_message=request.message,
            thread_id=thread_id,
            user_context=user_context
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


@app.post("/api/analytics", response_model=AnalyticsResponse)
async def analytics_endpoint(
    request: AnalyticsRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    Analytics endpoint for data analysis, reporting, and visualization

    Headers (if API_KEY is configured in .env):
        X-API-Key: your_api_key

    Expected payload:
    {
        "query": "Natural language query for analytics",
        "user_id": "optional-user-id",
        "user_role": "optional-user-role (admin/manager/engineer/viewer/guest)",
        "metadata": {}
    }

    Returns:
    {
        "type": "text|table|chart|mixed",
        "content": "Result data (format depends on type)",
        "sql_query": "SQL query used (for transparency)",
        "chart_config": "Chart.js configuration (if type=chart)",
        "metadata": {
            "row_count": 10,
            "execution_time": 0.123
        },
        "success": true
    }

    Examples:
    - "Покажи количество проектов по статусам" → returns chart with pie chart config
    - "Статистика завершенных объектов за последний месяц" → returns table
    - "Сравни прогресс проектов" → returns comparison table
    """
    try:
        from database.supabase_client import supabase_db_client

        logger.info(f"📊 Received analytics request: query='{request.query}', user_id={request.user_id}")

        # Get analytics agent
        agent_instance = get_analytics_agent()

        # Determine user role for RBAC
        user_role = request.user_role

        if not user_role and request.user_id:
            # Load user role from database
            if supabase_db_client.is_available():
                user_context = supabase_db_client.get_user_profile(request.user_id)
                if user_context:
                    user_role = user_context.get('role_name', 'guest')
                    logger.info(f"Loaded user role from DB: {user_role}")
                else:
                    user_role = 'guest'
                    logger.warning(f"No profile found for user_id={request.user_id}, using guest role")
            else:
                user_role = 'guest'
                logger.warning("Supabase not available, using guest role")
        elif not user_role:
            user_role = 'guest'
            logger.info("No user_role or user_id provided, using guest role")

        # Process analytics query
        logger.info(f"Processing analytics query with role: {user_role}")
        result: AnalyticsResult = agent_instance.process_analytics(
            user_query=request.query,
            user_role=user_role
        )

        logger.info(f"Analytics result generated: type={result.type}, rows={result.metadata.get('row_count', 0)}")

        # Create response
        response = AnalyticsResponse(
            type=result.type,
            content=result.content,
            sql_query=result.sql_query,
            chart_config=result.chart_config,
            metadata=result.metadata,
            success=True
        )

        return response

    except Exception as e:
        logger.error(f"Error processing analytics request: {e}", exc_info=True)
        return AnalyticsResponse(
            type="text",
            content=f"Произошла ошибка при обработке аналитического запроса: {str(e)}",
            metadata={"error": str(e)},
            success=False,
            error=str(e)
        )


@app.post("/api/teams/process-meeting", response_model=TeamsProcessResponse)
async def teams_process_meeting(
    request: TeamsProcessRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    Process a Teams meeting transcript and generate a structured Notion-style report.

    Headers (if API_KEY is configured in .env):
        X-API-Key: your_api_key

    Expected payload:
    {
        "meeting": {
            "title": "Meeting title",
            "date": "2026-03-10",
            "duration": "1h 30m",
            "participants": [{"name": "...", "role": "..."}],
            "transcript": [{"speaker": "...", "timestamp": "00:01:30", "text": "..."}]
        },
        "user_id": "optional-user-id",
        "metadata": {}
    }

    Returns:
    {
        "report": { ... MeetingReport ... },
        "success": true,
        "metadata": {"participants_count": 5, "segments_count": 20}
    }
    """
    try:
        logger.info(f"Received Teams meeting request: title='{request.meeting.title}', "
                     f"participants={len(request.meeting.participants)}, "
                     f"segments={len(request.meeting.transcript)}")

        agent_instance = get_teams_agent()

        author = _build_author_from_conversation(request.teams_conversation_id)

        loop = asyncio.get_event_loop()
        report = await loop.run_in_executor(
            None, agent_instance.process_meeting, request.meeting, author
        )

        logger.info(f"Meeting report generated: {len(report.discussion_items)} discussion items, "
                     f"{len(report.open_questions)} open questions, "
                     f"{len(report.risks)} risks")

        # Send report to Teams if configured and requested
        teams_sent = False
        if request.send_to_teams and teams_sender.is_configured:
            try:
                report_text = format_report_as_text(report)

                if request.teams_conversation_id:
                    # Send to specific conversation
                    await teams_sender.send_message(request.teams_conversation_id, report_text)
                    teams_sent = True
                    logger.info(f"Report sent to Teams conversation {request.teams_conversation_id}")
                else:
                    # Send to all saved conversations
                    conversations = teams_sender.list_conversations()
                    if conversations:
                        results = await teams_sender.send_report_to_all(report_text)
                        teams_sent = any(r["success"] for r in results)
                        logger.info(f"Report broadcast to {len(results)} conversations")
                    else:
                        logger.warning("No Teams conversations saved. "
                                       "Someone must write to the bot first.")
            except Exception as e:
                logger.error(f"Failed to send report to Teams: {e}")

        return TeamsProcessResponse(
            report=report,
            success=True,
            metadata={
                "participants_count": len(request.meeting.participants),
                "segments_count": len(request.meeting.transcript),
                "teams_sent": teams_sent,
            }
        )

    except Exception as e:
        logger.error(f"Error processing Teams meeting: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error processing meeting: {str(e)}"
        )


@app.post("/api/messages")
async def teams_messages_endpoint(request: Request):
    """
    Bot Framework messaging endpoint.
    Receives activities from Microsoft Teams when users write to the bot.
    This is the URL you set in Azure Bot → Configuration → Messaging endpoint.

    When a user writes to the bot in Teams:
    1. Microsoft sends the activity here
    2. We save the conversation reference (so we can message back later)
    3. We reply with a greeting
    """
    try:
        activity = await request.json()
        activity_type = activity.get("type", "")

        logger.info(f"Teams activity received: type={activity_type}, "
                     f"from={activity.get('from', {}).get('name', 'unknown')}")

        if activity_type == "message":
            # Save conversation reference for future proactive messages
            teams_sender.save_conversation_reference(activity)

            user_name = activity.get("from", {}).get("name", "пользователь")
            text = activity.get("text", "").strip()

            # Check for meeting links
            meeting_url = extract_meeting_url(text)

            if meeting_url:
                logger.info(f"Meeting link detected from {user_name}: {meeting_url}")

                # Get conversation ID to send report back to later
                conversation_id = activity.get("conversation", {}).get("id")

                if recall_client.is_configured:
                    try:
                        result = await recall_client.join_meeting(
                            meeting_url=meeting_url,
                            teams_conversation_id=conversation_id,
                        )
                        recall_bot_id = result.get("id", "unknown")
                        reply_text = (
                            "Вижу ссылку на созвон. Отправляю ассистента для записи. "
                            "По завершении пришлю протокол сюда."
                        )
                        logger.info(f"Recall bot {recall_bot_id} sent to {meeting_url}")
                    except Exception as e:
                        logger.error(f"Failed to send Recall bot: {e}")
                        reply_text = f"Не удалось отправить ассистента на встречу: {e}"
                else:
                    reply_text = (
                        "Вижу ссылку на созвон, но Recall AI не настроен (RECALL_API_KEY). "
                        "Добавьте ключ в .env для автоматической записи."
                    )

                await teams_sender.reply_to_activity(activity, reply_text)

            else:
                # Default greeting
                reply_text = (
                    f"Привет, {user_name}! Я Eneca Meeting Bot.\n\n"
                    f"Я сохранил ваш чат — теперь отчёты по встречам будут приходить сюда.\n\n"
                    f"Отправьте мне ссылку на встречу (Teams, Zoom, Google Meet) — "
                    f"и я запишу и пришлю протокол."
                )
                await teams_sender.reply_to_activity(activity, reply_text)

        elif activity_type == "conversationUpdate":
            # Bot was added to conversation
            members_added = activity.get("membersAdded", [])
            bot_id = activity.get("recipient", {}).get("id")
            for member in members_added:
                if member.get("id") != bot_id:
                    # A user was added, save reference
                    teams_sender.save_conversation_reference(activity)

        # Return 200 OK (required by Bot Framework)
        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error processing Teams activity: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@app.get("/api/teams/conversations")
async def teams_conversations(api_key: str = Depends(verify_api_key)):
    """List all saved conversation references (for debugging)"""
    return {
        "conversations": teams_sender.list_conversations(),
        "is_configured": teams_sender.is_configured,
    }


@app.get("/api/teams/test-auth")
async def teams_test_auth():
    """Test Microsoft OAuth token acquisition — for debugging"""
    import httpx
    tenant = settings.tenant_id or "botframework.com"
    oauth_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                oauth_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.microsoft_app_id,
                    "client_secret": settings.microsoft_app_password,
                    "scope": "https://api.botframework.com/.default",
                },
            )
            return {
                "app_id": settings.microsoft_app_id,
                "tenant_id": tenant,
                "url": oauth_url,
                "status": response.status_code,
                "body": response.json(),
            }
    except Exception as e:
        return {"app_id": settings.microsoft_app_id, "error": str(e)}


@app.get("/api/recall/webhook")
async def recall_webhook_health():
    """Health check for Recall webhook URL validation"""
    return {"status": "ok"}


@app.post("/api/recall/webhook")
async def recall_webhook(request: Request):
    """
    Webhook endpoint for Recall.ai events.

    Register this URL in Recall dashboard:
        https://your-server.com/api/recall/webhook

    Flow:
    1. Recall sends bot.status_change event (status: done)
    2. We fetch the transcript from Recall API
    3. Convert to MeetingTranscript format
    4. Process with TeamsAgent
    5. Send report to the original Teams conversation
    """
    try:
        data = await request.json()
        event = data.get("event", "")

        # Log full webhook payload for debugging
        logger.info(f"Recall webhook FULL payload: {json.dumps(data, default=str)}")

        # Recall sends bot_id in data.bot.id
        bot_id = str(
            data.get("data", {}).get("bot", {}).get("id", "")
            or data.get("data", {}).get("bot_id", "")
            or ""
        )

        logger.info(f"Recall webhook received: event={event}, bot_id={bot_id}")

        # Handle recording.done — start Whisper transcription
        if event == "recording.done":
            if bot_id:
                logger.info(f"Recording done for bot {bot_id}, starting Whisper transcription")
                asyncio.create_task(_process_recording_with_whisper(bot_id))
            else:
                logger.warning("recording.done without bot_id")

        # Handle transcript.done — ignore (using Whisper)
        elif event == "transcript.done":
            logger.info(f"Recall transcript.done for bot {bot_id} (ignored, using Whisper)")

        # Handle bot.done — just log
        elif event == "bot.done":
            logger.info(f"Bot {bot_id} done")

        # Handle fatal errors
        elif event == "bot.status_change":
            status = data.get("data", {}).get("status", {})
            code = status.get("code", "")
            logger.info(f"Recall bot {bot_id} status: {code}")

            if code == "fatal":
                logger.error(f"Recall bot {bot_id} failed: {status}")
                conversation_id = recall_client.get_conversation_for_bot(bot_id)
                if conversation_id:
                    try:
                        await teams_sender.send_message(
                            conversation_id,
                            f"Ассистент не смог записать встречу. Ошибка: {status.get('message', 'unknown')}"
                        )
                    except Exception as e:
                        logger.error(f"Failed to notify about Recall failure: {e}")

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error processing Recall webhook: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


async def _process_recording_with_whisper(bot_id: str):
    """
    Background task: download video from Recall, transcribe with Whisper,
    enrich with speaker names from Recall speaker_timeline,
    process with TeamsAgent, send report to Teams.
    """
    conversation_id = recall_client.get_conversation_for_bot(bot_id)

    try:
        logger.info(f"Processing recording for bot {bot_id} via Whisper")

        # Notify user that processing has started
        if conversation_id and teams_sender.is_configured:
            await teams_sender.send_message(
                conversation_id,
                "Встреча завершена. Обрабатываю запись..."
            )

        # 1. Download video from Recall
        video_path = await recall_client.download_video(bot_id)
        if not video_path:
            raise ValueError("Failed to download video from Recall")

        # 2. Transcribe with OpenAI Whisper
        loop = asyncio.get_event_loop()
        whisper_result = await loop.run_in_executor(
            None, whisper_transcriber.transcribe, video_path
        )

        segments = whisper_result.get("segments", [])
        logger.info(f"Whisper transcription: {len(segments)} segments")

        if not segments:
            raise ValueError("Whisper returned 0 segments — no speech detected")

        # 3. Get speaker timeline from Recall to map speakers to Whisper segments
        speaker_timeline = await recall_client.get_speaker_timeline(bot_id)
        if speaker_timeline:
            timeline_names = list(set(
                e.get("participant", {}).get("name", "?") for e in speaker_timeline
            ))
            logger.info(f"Recall speaker_timeline: {len(speaker_timeline)} entries, "
                        f"participants: {timeline_names}")
            for i, entry in enumerate(speaker_timeline):
                name = entry.get("participant", {}).get("name", "?")
                start = entry.get("start_timestamp", {}).get("relative", 0)
                end = entry.get("end_timestamp", {}).get("relative", 0)
                logger.info(f"  timeline[{i}]: {start:.1f}s - {end:.1f}s → {name}")
        else:
            logger.warning(f"Recall speaker_timeline is EMPTY for bot {bot_id} "
                           "— all segments will be labeled 'Speaker'")

        def _get_speaker_for_segment(seg_start: float, seg_end: float) -> str:
            """Find who was speaking during a segment by max overlap with speaker_timeline."""
            if not speaker_timeline:
                return "Speaker"

            # Calculate overlap duration with each speaker
            speaker_overlap: dict[str, float] = {}
            for entry in speaker_timeline:
                tl_start = entry.get("start_timestamp", {}).get("relative", 0)
                tl_end = entry.get("end_timestamp", {}).get("relative", 0)
                overlap = max(0, min(seg_end, tl_end) - max(seg_start, tl_start))
                if overlap > 0:
                    name = entry.get("participant", {}).get("name", "Speaker")
                    speaker_overlap[name] = speaker_overlap.get(name, 0) + overlap

            if speaker_overlap:
                return max(speaker_overlap, key=speaker_overlap.get)

            # No overlap — find nearest speaker by time distance
            best_name = "Speaker"
            best_dist = float("inf")
            for entry in speaker_timeline:
                tl_start = entry.get("start_timestamp", {}).get("relative", 0)
                tl_end = entry.get("end_timestamp", {}).get("relative", 0)
                dist = min(abs(seg_start - tl_end), abs(seg_end - tl_start))
                if dist < best_dist:
                    best_dist = dist
                    best_name = entry.get("participant", {}).get("name", "Speaker")
            return best_name

        # Assign speaker names to Whisper segments using max overlap
        for seg in segments:
            seg_start = seg.get("start_sec", 0)
            seg_end = seg.get("end_sec", seg_start)
            seg["speaker"] = _get_speaker_for_segment(seg_start, seg_end)

        # 4. Get meeting metadata from Recall
        bot_data = await recall_client.get_bot_status(bot_id)

        meeting_metadata = (
            bot_data.get("recordings", [{}])[0]
            .get("media_shortcuts", {})
            .get("meeting_metadata", {})
            .get("data", {})
        )
        title = meeting_metadata.get("title") or "Meeting Recording"
        date = bot_data.get("join_at", "")[:10] if bot_data.get("join_at") else ""

        # Collect unique speaker names from segments
        unique_speakers = list(set(seg["speaker"] for seg in segments))
        generic_count = sum(1 for seg in segments if seg["speaker"] == "Speaker")
        logger.info(f"Speakers detected: {unique_speakers}")
        logger.info(f"Speaker assignment stats: {len(segments) - generic_count}/{len(segments)} "
                    f"segments mapped to real speakers, {generic_count} remained generic 'Speaker'")

        # Log full transcript with speakers for debugging
        logger.info("=== FULL TRANSCRIPT WITH SPEAKERS ===")
        for seg in segments:
            logger.info(f"  [{seg['timestamp']}] {seg['speaker']}: {seg['text']}")
        logger.info("=== END TRANSCRIPT ===")

        # Build MeetingTranscript
        meeting = MeetingTranscript(
            title=title,
            date=date,
            duration=None,
            participants=[
                MeetingParticipant(name=name, role=None)
                for name in unique_speakers
            ],
            transcript=[
                TranscriptSegment(
                    speaker=seg["speaker"],
                    timestamp=seg["timestamp"],
                    text=seg["text"],
                )
                for seg in segments
            ],
        )

        # 4. Process with TeamsAgent
        agent_instance = get_teams_agent()
        author = _build_author_from_conversation(conversation_id)
        report = await loop.run_in_executor(
            None, agent_instance.process_meeting, meeting, author
        )

        logger.info(f"Report generated for bot {bot_id}: "
                     f"{len(report.discussion_items)} discussion items, "
                     f"{len(report.open_questions)} open questions, "
                     f"{len(report.risks)} risks")

        # 5. Send report to Teams
        if conversation_id and teams_sender.is_configured:
            report_text = format_report_as_text(report)
            await teams_sender.send_message(conversation_id, report_text)
            logger.info(f"Report sent to Teams conversation {conversation_id}")
        else:
            logger.warning(f"No Teams conversation mapped for bot {bot_id}")

        # 6. Clean up temp video file
        import os
        try:
            os.remove(video_path)
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Error processing recording for bot {bot_id}: {e}",
                     exc_info=True)
        if conversation_id and teams_sender.is_configured:
            try:
                await teams_sender.send_message(
                    conversation_id,
                    f"Ошибка при обработке записи встречи: {str(e)}"
                )
            except Exception:
                pass


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
