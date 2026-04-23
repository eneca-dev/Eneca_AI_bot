"""Teams Agent for processing meeting transcripts and generating structured reports.

Schema follows the Eneca corporate protocol template
('2026.03.09 Шаблон протокола совещания'):
- Header block (subject / date / location / project / transcript link / previous protocol / participants)
- Section 1: Обсужденные вопросы, договоренности и действия (flat DiscussionItem list)
- Section 2: Открытые вопросы
- Section 3: Риски
- Author block

Caller-supplied metadata (author, location, transcript_url, previous_protocol_url)
is attached after the LLM call so the model cannot hallucinate it.
"""
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
    """Meeting participant info. Mirrors the 'Участники' table columns in the template."""
    model_config = ConfigDict(extra="forbid")

    organization: Optional[str] = Field(None, description="Organization — only if explicitly mentioned in the transcript")
    name: str = Field(description="Full name of the participant")
    role: Optional[str] = Field(None, description="Role / job title")


class MeetingTranscript(BaseModel):
    """Complete meeting transcript input."""
    model_config = ConfigDict(extra="forbid")

    title: str = Field(description="Meeting title")
    date: str = Field(description="Meeting date in ISO format")
    duration: Optional[str] = Field(None, description="Meeting duration (e.g., '1h 30m')")
    participants: List[MeetingParticipant] = Field(description="List of participants")
    transcript: List[TranscriptSegment] = Field(description="Ordered transcript segments")


# --- Output Models ---

class Author(BaseModel):
    """Protocol author. Filled by the caller from the Teams conversation reference."""
    organization: Optional[str] = Field(None, description="Organization of the author")
    name: str = Field(description="Author full name")
    role: Optional[str] = Field(None, description="Author job title")


class DiscussionItem(BaseModel):
    """One row of section 1 'Обсужденные вопросы, договоренности и действия'.

    Flat structure — one row per discussed topic. Decisions and actions
    are merged into `outcome` (the template has no separate 'decisions' section).
    """
    topic: str = Field(description="Вопрос / тема")
    outcome: str = Field(description="Итог / действие — объединяет решение и действие в одном поле")
    responsible: Optional[str] = Field(None, description="Ответственный")
    deadline: Optional[str] = Field(None, description="Срок (без предлога 'до')")
    status: str = Field(default="Новый", description="Новый / В работе / Выполнено / Отложено")


class OpenQuestion(BaseModel):
    """Row of section 2 'Открытые вопросы'."""
    question: str = Field(description="Вопрос")
    responsible: Optional[str] = Field(None, description="Ответственный")
    deadline: Optional[str] = Field(None, description="Срок получения ответа")
    comment: Optional[str] = Field(None, description="Комментарий")


class Risk(BaseModel):
    """Row of section 3 'Риски'."""
    risk: str = Field(description="Риск")
    cause: Optional[str] = Field(None, description="Причина")
    consequences: Optional[str] = Field(None, description="Возможные последствия")
    responsible: Optional[str] = Field(None, description="Ответственный")
    mitigation: Optional[str] = Field(None, description="Действие / митигация")


class LLMMeetingReport(BaseModel):
    """Part of the protocol that the LLM fills from the transcript.

    Caller-supplied fields (date, duration, location, urls, author) are NOT
    exposed to the model — they are attached later in `process_meeting`.
    """
    subject: str = Field(description="Предмет совещания")
    project: Optional[str] = Field(None, description="Проект — заполнять только если явно упомянут в транскрипте")
    participants: List[MeetingParticipant] = Field(description="Участники")
    preview_summary: Optional[str] = Field(
        None,
        description="2-3 предложения для превью в Teams; не является частью формального протокола",
    )
    discussion_items: List[DiscussionItem] = Field(description="Раздел 1 — плоский список")
    open_questions: List[OpenQuestion] = Field(description="Раздел 2 — открытые вопросы (пустой список если нет)")
    risks: List[Risk] = Field(description="Раздел 3 — риски (пустой список если нет)")


class MeetingReport(LLMMeetingReport):
    """Complete protocol: LLM output + caller-supplied metadata."""
    date: str = Field(description="Дата встречи (копируется из входа)")
    duration: Optional[str] = Field(None, description="Длительность (копируется из входа)")
    location: str = Field(default="Microsoft Teams", description="Место проведения")
    transcript_url: Optional[str] = Field(None, description="Ссылка на транскрибацию")
    previous_protocol_url: Optional[str] = Field(None, description="Ссылка на протокол предшествующего совещания")
    author: Author = Field(description="Составитель")


DEFAULT_AUTHOR = Author(
    organization="Eneca",
    name="Meeting Bot",
    role="Автоматический протокол",
)


class TeamsAgent(BaseAgent):
    """Teams Agent for processing meeting transcripts and generating structured reports."""

    def __init__(self, model: str = None, temperature: float = None):
        model = model or settings.teams_agent_model
        temperature = temperature if temperature is not None else 0.2

        super().__init__(model=model, temperature=temperature)

        # LLM returns the subset of fields it is responsible for;
        # caller-supplied metadata (author, location, urls, date, duration) is attached afterwards.
        self.report_llm = self.llm.with_structured_output(LLMMeetingReport)

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
        return (
            "Ты — Teams Agent. Формируй протокол встречи по корпоративному шаблону Eneca: "
            "шапка + раздел 1 «Обсужденные вопросы / итог / ответственный / срок / статус», "
            "раздел 2 «Открытые вопросы», раздел 3 «Риски». Отчёт на русском. "
            "Опирайся только на содержание транскрипта."
        )

    def _prepare_transcript_text(self, meeting: MeetingTranscript) -> str:
        """Format meeting transcript into a text prompt for the LLM"""
        parts = [f"# Встреча: {meeting.title}", f"Дата: {meeting.date}"]
        if meeting.duration:
            parts.append(f"Длительность: {meeting.duration}")

        parts.append("\n## Участники:")
        for p in meeting.participants:
            org = f"[{p.organization}] " if p.organization else ""
            role_str = f" ({p.role})" if p.role else ""
            parts.append(f"- {org}{p.name}{role_str}")

        parts.append("\n## Транскрипт:")
        for segment in meeting.transcript:
            parts.append(f"[{segment.timestamp}] {segment.speaker}: {segment.text}")

        return "\n".join(parts)

    def process_meeting(
        self,
        meeting: MeetingTranscript,
        author: Optional[Author] = None,
    ) -> MeetingReport:
        """Transcript → structured protocol aligned with the Eneca template.

        Args:
            meeting: Validated meeting transcript.
            author: Protocol author. Defaults to the Eneca meeting bot.
        """
        logger.info(f"Processing meeting: '{meeting.title}', {len(meeting.transcript)} segments")

        author = author or DEFAULT_AUTHOR

        try:
            from langchain_core.messages import SystemMessage, HumanMessage

            transcript_text = self._prepare_transcript_text(meeting)

            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=(
                    "Проанализируй следующую встречу и сформируй протокол по "
                    "корпоративному шаблону Eneca:\n\n" + transcript_text
                )),
            ]

            llm_report: LLMMeetingReport = self.report_llm.invoke(messages)

            report = MeetingReport(
                subject=llm_report.subject,
                project=llm_report.project,
                participants=llm_report.participants,
                preview_summary=llm_report.preview_summary,
                discussion_items=llm_report.discussion_items,
                open_questions=llm_report.open_questions,
                risks=llm_report.risks,
                # Caller-supplied / authoritative from input
                date=meeting.date,
                duration=meeting.duration,
                location="Microsoft Teams",
                transcript_url=None,
                previous_protocol_url=None,
                author=author,
            )

            logger.info(
                f"Report generated: {len(report.discussion_items)} discussion items, "
                f"{len(report.open_questions)} open questions, {len(report.risks)} risks"
            )

            return report

        except Exception as e:
            logger.error(f"Error processing meeting: {e}")
            return MeetingReport(
                subject=meeting.title,
                date=meeting.date,
                duration=meeting.duration,
                project=None,
                participants=meeting.participants,
                preview_summary=f"Ошибка при обработке встречи: {str(e)}",
                discussion_items=[],
                open_questions=[],
                risks=[],
                location="Microsoft Teams",
                transcript_url=None,
                previous_protocol_url=None,
                author=author,
            )

    def process_meeting_raw(
        self,
        meeting_json: dict,
        author: Optional[Author] = None,
    ) -> dict:
        """Convenience: dict in, dict out."""
        meeting = MeetingTranscript(**meeting_json)
        report = self.process_meeting(meeting, author=author)
        return report.model_dump()
