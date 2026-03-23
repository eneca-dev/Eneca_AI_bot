"""Teams Agent for processing meeting transcripts and generating structured reports"""
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict
from agents.base import BaseAgent
from core.config import settings
from loguru import logger


# --- Input Models ---

class TranscriptSegment(BaseModel):
    """Single speech segment from the meeting transcript"""
    model_config = ConfigDict(extra="forbid")

    speaker: str = Field(description="Speaker name")
    timestamp: str = Field(description="Timestamp in format HH:MM:SS or MM:SS")
    text: str = Field(description="Speech content")


class MeetingParticipant(BaseModel):
    """Meeting participant info"""
    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Full name of the participant")
    role: Optional[str] = Field(None, description="Role/position of the participant")


class MeetingTranscript(BaseModel):
    """Complete meeting transcript input"""
    model_config = ConfigDict(extra="forbid")

    title: str = Field(description="Meeting title")
    date: str = Field(description="Meeting date in ISO format")
    duration: Optional[str] = Field(None, description="Meeting duration (e.g., '1h 30m')")
    participants: List[MeetingParticipant] = Field(description="List of participants")
    transcript: List[TranscriptSegment] = Field(description="Ordered transcript segments")


# --- Output Models ---

class ActionItem(BaseModel):
    """Action item extracted from the meeting"""
    description: str = Field(description="What needs to be done")
    assignee: Optional[str] = Field(None, description="Person responsible")
    deadline: Optional[str] = Field(None, description="Deadline if mentioned")
    priority: Optional[str] = Field(None, description="Priority: high/medium/low")


class FollowUpItem(BaseModel):
    """Follow-up item to check or revisit later"""
    description: str = Field(description="What to follow up on")
    owner: Optional[str] = Field(None, description="Who should follow up")
    context: Optional[str] = Field(None, description="Why this needs follow-up")


class DiscussionTopic(BaseModel):
    """A thematic discussion block with detailed breakdown"""
    topic: str = Field(description="Dynamic topic name based on discussion content")
    summary: str = Field(description="Overview of what was discussed")
    details: List[str] = Field(description="Key points with context and specifics")
    participants_involved: List[str] = Field(description="Who participated in this topic")


class SpeakerHighlight(BaseModel):
    """Compact speaker contribution summary"""
    speaker: str = Field(description="Speaker name")
    key_contributions: List[str] = Field(description="Main points, proposals, and positions")
    activity_level: Optional[str] = Field(None, description="Estimated activity, e.g. '~30% встречи'")


class MeetingReport(BaseModel):
    """Structured meeting report combining Notion-style and speaker-centric approaches"""
    title: str = Field(description="Meeting title")
    date: str = Field(description="Meeting date")
    duration: Optional[str] = Field(None, description="Meeting duration")
    participants: List[MeetingParticipant] = Field(description="Participants list")
    executive_summary: str = Field(description="2-3 sentence executive summary")
    action_items: List[ActionItem] = Field(description="Action items with assignees and deadlines")
    key_decisions: List[str] = Field(description="Key decisions made during the meeting")
    discussion_topics: List[DiscussionTopic] = Field(description="Thematic discussion blocks with details")
    speaker_highlights: List[SpeakerHighlight] = Field(description="Compact per-speaker contributions")
    follow_up: List[FollowUpItem] = Field(description="Items to revisit or check later")
    key_takeaways: List[str] = Field(description="Key takeaways and insights")


class TeamsAgent(BaseAgent):
    """
    Teams Agent for processing meeting transcripts and generating structured reports.

    Capabilities:
    - Analyze conference transcripts by speakers
    - Extract key moments, decisions, and action items
    - Generate Notion-style structured meeting reports
    """

    def __init__(self, model: str = None, temperature: float = None):
        model = model or settings.orchestrator_model
        temperature = temperature if temperature is not None else 0.2

        super().__init__(model=model, temperature=temperature)

        self.report_llm = self.llm.with_structured_output(MeetingReport)

        logger.info(f"TeamsAgent initialized with model {model}")

    def _get_default_prompt(self) -> str:
        """Load system prompt from prompts/teams_agent.md"""
        prompt_path = Path(__file__).parent.parent / "prompts" / "teams_agent.md"

        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                prompt = f.read()
            logger.debug(f"Loaded Teams agent prompt from {prompt_path}")
            return prompt
        except FileNotFoundError:
            logger.warning(f"Prompt file not found at {prompt_path}, using fallback")
            return self._get_fallback_prompt()

    def _get_fallback_prompt(self) -> str:
        """Fallback prompt if file not found"""
        return """Ты — Teams Agent для обработки и анализа совещаний в системе Eneca.

Твоя задача: анализировать транскрипты конференций и генерировать структурированные отчёты.

Формат отчёта:
1. Executive Summary — краткое резюме встречи (2-3 предложения)
2. Action Items & Next Steps — задачи с ответственными и дедлайнами
3. Ключевые решения — только явные, подтверждённые решения
4. Тематические блоки — динамические секции по содержанию с деталями
5. По спикерам — ключевые тезисы каждого участника
6. Follow-up — что нужно проверить или обсудить позже
7. Ключевые выводы — главные инсайты

ВАЖНО:
- Опирайся только на содержание транскрипта
- Отчёт на русском языке
- Сохраняй оригинальные имена спикеров
"""

    def _prepare_transcript_text(self, meeting: MeetingTranscript) -> str:
        """Format meeting transcript into a text prompt for the LLM"""
        parts = []

        # Meeting metadata
        parts.append(f"# Встреча: {meeting.title}")
        parts.append(f"Дата: {meeting.date}")
        if meeting.duration:
            parts.append(f"Длительность: {meeting.duration}")

        # Participants
        parts.append("\n## Участники:")
        for p in meeting.participants:
            role_str = f" ({p.role})" if p.role else ""
            parts.append(f"- {p.name}{role_str}")

        # Transcript
        parts.append("\n## Транскрипт:")
        for segment in meeting.transcript:
            parts.append(f"[{segment.timestamp}] {segment.speaker}: {segment.text}")

        return "\n".join(parts)

    def process_meeting(self, meeting: MeetingTranscript) -> MeetingReport:
        """
        Main processing pipeline: analyze transcript and generate structured report.

        Args:
            meeting: Validated meeting transcript

        Returns:
            Structured MeetingReport
        """
        logger.info(f"Processing meeting: '{meeting.title}', {len(meeting.transcript)} segments")

        try:
            from langchain_core.messages import SystemMessage, HumanMessage

            transcript_text = self._prepare_transcript_text(meeting)

            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=f"Проанализируй следующую встречу и создай структурированный отчёт:\n\n{transcript_text}")
            ]

            report = self.report_llm.invoke(messages)

            logger.info(f"Report generated: {len(report.action_items)} action items, "
                        f"{len(report.key_decisions)} decisions")

            return report

        except Exception as e:
            logger.error(f"Error processing meeting: {e}")
            # Return a minimal fallback report
            return MeetingReport(
                title=meeting.title,
                date=meeting.date,
                duration=meeting.duration,
                executive_summary=f"Ошибка при обработке встречи: {str(e)}",
                participants=meeting.participants,
                action_items=[],
                key_decisions=[],
                discussion_topics=[],
                speaker_highlights=[],
                follow_up=[],
                key_takeaways=[],
            )

    def process_meeting_raw(self, meeting_json: dict) -> dict:
        """
        Convenience method: accepts raw dict, returns dict.

        Args:
            meeting_json: Raw meeting data as dict

        Returns:
            Report as dict
        """
        meeting = MeetingTranscript(**meeting_json)
        report = self.process_meeting(meeting)
        return report.model_dump()
