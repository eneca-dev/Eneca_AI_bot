"""Service for sending messages to Microsoft Teams via Bot Framework REST API"""
import time
import httpx
from typing import Optional
from loguru import logger
from core.config import settings


class TeamsSender:
    """
    Sends messages to Teams using Bot Framework REST API.

    Flow:
    1. Get OAuth token from Microsoft (cached until expiry)
    2. Use token to send messages via Bot Connector API
    """

    OAUTH_SCOPE = "https://api.botframework.com/.default"

    def __init__(self):
        self._token: Optional[str] = None
        self._token_expires_at: float = 0
        # conversation_references stored by user AAD id or conversation id
        self._conversation_references: dict = {}
        logger.info("TeamsSender initialized")

    @property
    def is_configured(self) -> bool:
        return bool(settings.microsoft_app_id and settings.microsoft_app_password)

    async def _get_token(self) -> str:
        """Get OAuth token from Microsoft, with caching"""
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token

        if not self.is_configured:
            raise ValueError("MICROSOFT_APP_ID and MICROSOFT_APP_PASSWORD must be set in .env")

        # Use tenant-specific URL if TENANT_ID is set, otherwise fallback
        tenant = settings.tenant_id or "botframework.com"
        oauth_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                oauth_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.microsoft_app_id,
                    "client_secret": settings.microsoft_app_password,
                    "scope": self.OAUTH_SCOPE,
                },
            )
            if response.status_code != 200:
                logger.error(f"OAuth failed: {response.status_code} {response.text}")
                response.raise_for_status()
            data = response.json()
            logger.info(f"OAuth token acquired via {oauth_url}")

        self._token = data["access_token"]
        self._token_expires_at = time.time() + data.get("expires_in", 3600)
        logger.info("Bot Framework OAuth token acquired")
        return self._token

    def save_conversation_reference(self, activity: dict):
        """
        Save conversation reference from incoming activity.
        Called when user writes to the bot for the first time.
        """
        conversation = activity.get("conversation", {})
        conv_id = conversation.get("id")
        from_user = activity.get("from", {})

        ref = {
            "conversation_id": conv_id,
            "service_url": activity.get("serviceUrl"),
            "bot_id": activity.get("recipient", {}).get("id"),
            "bot_name": activity.get("recipient", {}).get("name"),
            "user_id": from_user.get("id"),
            "user_name": from_user.get("name"),
            "user_aad_object_id": from_user.get("aadObjectId"),
            "channel_id": activity.get("channelId"),
        }

        # Store by conversation_id and by user AAD id
        self._conversation_references[conv_id] = ref
        if from_user.get("aadObjectId"):
            self._conversation_references[from_user["aadObjectId"]] = ref

        logger.info(f"Saved conversation reference for user '{ref['user_name']}' "
                     f"(conv_id={conv_id})")

    def get_conversation_reference(self, identifier: str) -> Optional[dict]:
        """Get saved conversation reference by conversation_id or user AAD id"""
        return self._conversation_references.get(identifier)

    def list_conversations(self) -> list:
        """List all saved conversation references (for debugging)"""
        seen = set()
        result = []
        for ref in self._conversation_references.values():
            conv_id = ref["conversation_id"]
            if conv_id not in seen:
                seen.add(conv_id)
                result.append({
                    "conversation_id": conv_id,
                    "user_name": ref.get("user_name"),
                    "user_aad_object_id": ref.get("user_aad_object_id"),
                })
        return result

    async def send_message(self, conversation_id: str, text: str, service_url: str = None) -> dict:
        """
        Send a text message to a Teams conversation.

        Args:
            conversation_id: Target conversation ID
            text: Message text (supports markdown)
            service_url: Bot Framework service URL (from conversation reference)
        """
        # Find service_url from saved references if not provided
        if not service_url:
            ref = self._conversation_references.get(conversation_id)
            if ref:
                service_url = ref["service_url"]
            else:
                raise ValueError(f"No conversation reference found for {conversation_id}. "
                                 "User must write to the bot first.")

        token = await self._get_token()

        url = f"{service_url}/v3/conversations/{conversation_id}/activities"

        payload = {
            "type": "message",
            "text": text,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            result = response.json()

        logger.info(f"Message sent to conversation {conversation_id}")
        return result

    async def send_to_user(self, user_identifier: str, text: str) -> dict:
        """
        Send a message to a specific user by their AAD id or conversation_id.
        User must have written to the bot at least once.
        """
        ref = self._conversation_references.get(user_identifier)
        if not ref:
            raise ValueError(
                f"No conversation reference for '{user_identifier}'. "
                "User must write to the bot first in Teams."
            )

        return await self.send_message(
            conversation_id=ref["conversation_id"],
            service_url=ref["service_url"],
            text=text,
        )

    async def send_report_to_all(self, text: str) -> list:
        """Send a message to all saved conversations (broadcast)"""
        results = []
        seen = set()
        for ref in self._conversation_references.values():
            conv_id = ref["conversation_id"]
            if conv_id in seen:
                continue
            seen.add(conv_id)
            try:
                result = await self.send_message(
                    conversation_id=conv_id,
                    service_url=ref["service_url"],
                    text=text,
                )
                results.append({"conversation_id": conv_id, "success": True, "result": result})
            except Exception as e:
                logger.error(f"Failed to send to {conv_id}: {e}")
                results.append({"conversation_id": conv_id, "success": False, "error": str(e)})
        return results

    async def reply_to_activity(self, activity: dict, text: str) -> dict:
        """Reply directly to an incoming activity"""
        service_url = activity.get("serviceUrl")
        conversation_id = activity.get("conversation", {}).get("id")
        activity_id = activity.get("id")

        token = await self._get_token()

        url = f"{service_url}/v3/conversations/{conversation_id}/activities"

        payload = {
            "type": "message",
            "text": text,
            "replyToId": activity_id,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            return response.json()


def format_report_as_text(report) -> str:
    """Format MeetingReport as readable text for Teams message"""
    lines = []

    # Header
    lines.append(f"**{report.title}**")
    lines.append(f"_{report.date}_ | {report.duration or 'N/A'}")
    lines.append("")
    lines.append(f"**Резюме:** {report.executive_summary}")
    lines.append("")

    # Action Items — most important, first
    if report.action_items:
        lines.append("**Action Items & Next Steps:**")
        for item in report.action_items:
            assignee = f" — **{item.assignee}**" if item.assignee else ""
            priority = f" [{item.priority}]" if item.priority else ""
            deadline = f" (до {item.deadline})" if item.deadline else ""
            lines.append(f"- [ ] {item.description}{assignee}{priority}{deadline}")
        lines.append("")

    # Key decisions
    if report.key_decisions:
        lines.append("**Ключевые решения:**")
        for d in report.key_decisions:
            lines.append(f"- {d}")
        lines.append("")

    # Discussion topics with details
    if report.discussion_topics:
        for topic in report.discussion_topics:
            lines.append(f"**{topic.topic}**")
            lines.append(f"{topic.summary}")
            if topic.details:
                for detail in topic.details:
                    lines.append(f"- {detail}")
            if topic.participants_involved:
                lines.append(f"_Участники: {', '.join(topic.participants_involved)}_")
            lines.append("")

    # Speaker highlights
    if report.speaker_highlights:
        lines.append("**По спикерам:**")
        for s in report.speaker_highlights:
            activity = f" ({s.activity_level})" if s.activity_level else ""
            lines.append(f"- **{s.speaker}**{activity}: {'; '.join(s.key_contributions[:3])}")
        lines.append("")

    # Follow-up
    if report.follow_up:
        lines.append("**Follow-up:**")
        for f in report.follow_up:
            owner = f" — {f.owner}" if f.owner else ""
            lines.append(f"- {f.description}{owner}")
        lines.append("")

    # Key takeaways
    if report.key_takeaways:
        lines.append("**Выводы:**")
        for t in report.key_takeaways:
            lines.append(f"- {t}")

    return "\n".join(lines)


# Singleton instance
teams_sender = TeamsSender()
