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


_DASH = "—"
_EMPTY_SECTION = "Нет"


def _val(v) -> str:
    """Render optional value as em dash when empty/None."""
    if v is None:
        return _DASH
    s = str(v).strip()
    return s if s else _DASH


def _format_header(report) -> list:
    lines = [
        f"**Протокол совещания от {_val(report.date)}**",
        "",
        f"**Место проведения:** {_val(report.location)}",
        f"**Дата:** {_val(report.date)}",
        f"**Проект:** {_val(report.project)}",
        f"**Транскрибация:** {_val(report.transcript_url)}",
        f"**Предмет совещания:** {_val(report.subject)}",
        f"**Ссылка на протокол предшествующего совещания:** {_val(report.previous_protocol_url)}",
        "",
        "**Участники:**",
    ]
    if report.participants:
        for i, p in enumerate(report.participants, 1):
            lines.append(
                f"{i}. Организация: {_val(p.organization)} | "
                f"ФИО: {_val(p.name)} | "
                f"Должность: {_val(p.role)}"
            )
    else:
        lines.append(_EMPTY_SECTION)
    return lines


def _format_numbered_section(title: str, items: list, render_item) -> list:
    """Render a numbered section. `render_item(item)` returns a list of lines (without leading '1.')."""
    lines = ["", f"**{title}**"]
    if not items:
        lines.append(_EMPTY_SECTION)
        return lines
    for i, item in enumerate(items, 1):
        item_lines = render_item(item)
        if not item_lines:
            continue
        lines.append(f"{i}. {item_lines[0]}")
        for extra in item_lines[1:]:
            lines.append(f"   {extra}")
    return lines


def _render_discussion_item(item) -> list:
    return [
        f"Вопрос/тема: {_val(item.topic)}",
        f"Итог/действие: {_val(item.outcome)}",
        f"Ответственный: {_val(item.responsible)}",
        f"Срок: {_val(item.deadline)}",
        f"Статус: {_val(item.status)}",
    ]


def _render_open_question(q) -> list:
    return [
        f"Вопрос: {_val(q.question)}",
        f"Ответственный: {_val(q.responsible)}",
        f"Срок получения ответа: {_val(q.deadline)}",
        f"Комментарий: {_val(q.comment)}",
    ]


def _render_risk(r) -> list:
    return [
        f"Риск: {_val(r.risk)}",
        f"Причина: {_val(r.cause)}",
        f"Возможные последствия: {_val(r.consequences)}",
        f"Ответственный: {_val(r.responsible)}",
        f"Действие: {_val(r.mitigation)}",
    ]


def _format_author(author) -> list:
    if author is None:
        return ["", f"**Составитель:** {_DASH}"]
    parts = [p for p in (author.organization, author.name, author.role) if p]
    return ["", f"**Составитель:** {', '.join(parts) if parts else _DASH}"]


def format_report_as_text(report) -> str:
    """Format MeetingReport as readable text following the Eneca protocol template."""
    lines = []
    lines.extend(_format_header(report))

    if report.preview_summary:
        lines.append("")
        lines.append(f"**Резюме:** {report.preview_summary}")

    lines.extend(_format_numbered_section(
        "1. Обсужденные вопросы, договоренности и действия",
        report.discussion_items,
        _render_discussion_item,
    ))
    lines.extend(_format_numbered_section(
        "2. Открытые вопросы",
        report.open_questions,
        _render_open_question,
    ))
    lines.extend(_format_numbered_section(
        "3. Риски",
        report.risks,
        _render_risk,
    ))
    lines.extend(_format_author(report.author))

    return "\n".join(lines)


# Singleton instance
teams_sender = TeamsSender()
