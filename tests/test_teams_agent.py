"""Tests for TeamsAgent — schema contract and text rendering.

These tests cover what we can verify without hitting the OpenAI API:
- Pydantic schema invariants (required fields, defaults)
- Text rendering of a known MeetingReport against the Eneca protocol template
"""
import pytest
from pydantic import ValidationError

from agents.teams_agent import (
    Author,
    DEFAULT_AUTHOR,
    DiscussionItem,
    MeetingParticipant,
    MeetingReport,
    OpenQuestion,
    Risk,
)
from services.teams_sender import format_report_as_text


# --- Schema contract ---


def test_meeting_report_requires_subject():
    with pytest.raises(ValidationError):
        MeetingReport(
            date="2026-04-23",
            participants=[],
            discussion_items=[],
            open_questions=[],
            risks=[],
            author=DEFAULT_AUTHOR,
        )


def test_meeting_report_requires_author():
    with pytest.raises(ValidationError):
        MeetingReport(
            subject="Sync",
            date="2026-04-23",
            participants=[],
            discussion_items=[],
            open_questions=[],
            risks=[],
        )


def test_meeting_report_accepts_minimal_body():
    """Empty body lists are valid — the template always renders all 3 sections."""
    report = MeetingReport(
        subject="Sync",
        date="2026-04-23",
        participants=[MeetingParticipant(name="Иван")],
        discussion_items=[],
        open_questions=[],
        risks=[],
        author=DEFAULT_AUTHOR,
    )
    assert report.location == "Microsoft Teams"
    assert report.transcript_url is None
    assert report.previous_protocol_url is None
    assert report.duration is None
    assert report.preview_summary is None


def test_discussion_item_status_defaults_to_new():
    item = DiscussionItem(topic="Foo", outcome="Bar")
    assert item.status == "Новый"


def test_meeting_participant_optional_fields():
    p = MeetingParticipant(name="Иван")
    assert p.organization is None
    assert p.role is None


def test_default_author_shape():
    assert DEFAULT_AUTHOR.organization == "Eneca"
    assert DEFAULT_AUTHOR.name == "Meeting Bot"
    assert DEFAULT_AUTHOR.role == "Автоматический протокол"


# --- Renderer golden tests ---


def _sample_report(**overrides) -> MeetingReport:
    defaults = dict(
        subject="Совещание по фундаментам",
        date="2026-04-23",
        location="Microsoft Teams",
        project="ЖК Северный",
        transcript_url=None,
        previous_protocol_url=None,
        duration="1h 5m",
        participants=[
            MeetingParticipant(organization="Eneca", name="Иван Петров", role="Инженер"),
            MeetingParticipant(organization=None, name="Мария Сидорова", role=None),
        ],
        preview_summary="Обсудили тип свай; решили использовать буронабивные.",
        discussion_items=[
            DiscussionItem(
                topic="Тип свай",
                outcome="Решено использовать буронабивные; Иван готовит спецификацию",
                responsible="Иван Петров",
                deadline="пятница",
                status="Новый",
            ),
            DiscussionItem(
                topic="Сроки поставки арматуры",
                outcome="Обсудили; решения не принято",
                responsible=None,
                deadline=None,
                status="Новый",
            ),
        ],
        open_questions=[
            OpenQuestion(
                question="Готовы ли результаты испытаний грунта?",
                responsible="Мария Сидорова",
                deadline="среда",
                comment="Нужны до начала работ",
            ),
        ],
        risks=[],
        author=Author(organization="Eneca", name="Иван Петров", role=None),
    )
    defaults.update(overrides)
    return MeetingReport(**defaults)


def test_renderer_header_shows_all_template_fields_with_dash_for_empty():
    text = format_report_as_text(_sample_report())

    assert "**Протокол совещания от 2026-04-23**" in text
    assert "**Место проведения:** Microsoft Teams" in text
    assert "**Дата:** 2026-04-23" in text
    assert "**Проект:** ЖК Северный" in text
    assert "**Транскрибация:** —" in text
    assert "**Предмет совещания:** Совещание по фундаментам" in text
    assert "**Ссылка на протокол предшествующего совещания:** —" in text


def test_renderer_participants_numbered_with_pipes():
    text = format_report_as_text(_sample_report())
    assert "1. Организация: Eneca | ФИО: Иван Петров | Должность: Инженер" in text
    assert "2. Организация: — | ФИО: Мария Сидорова | Должность: —" in text


def test_renderer_empty_participants_shows_placeholder():
    report = _sample_report(participants=[])
    text = format_report_as_text(report)
    header_idx = text.index("**Участники:**")
    assert text[header_idx:].splitlines()[1].strip() == "Нет"


def test_renderer_discussion_items_numbered_and_expanded():
    text = format_report_as_text(_sample_report())
    assert "**1. Обсужденные вопросы, договоренности и действия**" in text
    assert "1. Вопрос/тема: Тип свай" in text
    assert "   Итог/действие: Решено использовать буронабивные; Иван готовит спецификацию" in text
    assert "   Ответственный: Иван Петров" in text
    assert "   Срок: пятница" in text
    assert "   Статус: Новый" in text
    assert "2. Вопрос/тема: Сроки поставки арматуры" in text


def test_renderer_discussion_item_with_missing_fields_uses_dash():
    text = format_report_as_text(_sample_report())
    # The second discussion item has no responsible / deadline
    section = text.split("**1. Обсужденные вопросы")[1]
    second_item = section.split("2. Вопрос/тема:")[1]
    assert "Ответственный: —" in second_item
    assert "Срок: —" in second_item


def test_renderer_open_questions_block():
    text = format_report_as_text(_sample_report())
    assert "**2. Открытые вопросы**" in text
    assert "1. Вопрос: Готовы ли результаты испытаний грунта?" in text
    assert "   Ответственный: Мария Сидорова" in text
    assert "   Срок получения ответа: среда" in text
    assert "   Комментарий: Нужны до начала работ" in text


def test_renderer_empty_section_shows_placeholder():
    text = format_report_as_text(_sample_report())
    # risks list is empty → section shows "Нет"
    section_idx = text.index("**3. Риски**")
    section_line = text[section_idx:].splitlines()[1]
    assert section_line.strip() == "Нет"


def test_renderer_risks_rendered_when_present():
    report = _sample_report(risks=[
        Risk(
            risk="Задержка поставки арматуры",
            cause="Дефицит у поставщика",
            consequences="Сдвиг графика на 2 недели",
            responsible="Иван Петров",
            mitigation="Запасной поставщик",
        )
    ])
    text = format_report_as_text(report)
    assert "1. Риск: Задержка поставки арматуры" in text
    assert "   Причина: Дефицит у поставщика" in text
    assert "   Возможные последствия: Сдвиг графика на 2 недели" in text
    assert "   Ответственный: Иван Петров" in text
    assert "   Действие: Запасной поставщик" in text


def test_renderer_author_joins_nonempty_parts():
    text = format_report_as_text(_sample_report())
    # author.role is None → skipped
    assert "**Составитель:** Eneca, Иван Петров" in text


def test_renderer_author_all_empty_falls_back_to_dash():
    report = _sample_report(author=Author(name=""))
    text = format_report_as_text(report)
    assert "**Составитель:** —" in text


def test_renderer_preview_summary_rendered_when_present():
    text = format_report_as_text(_sample_report())
    assert "**Резюме:** Обсудили тип свай; решили использовать буронабивные." in text


def test_renderer_preview_summary_hidden_when_empty():
    report = _sample_report(preview_summary=None)
    text = format_report_as_text(report)
    assert "**Резюме:**" not in text


def test_renderer_section_order_matches_template():
    text = format_report_as_text(_sample_report())
    idx_header = text.index("**Протокол совещания")
    idx_participants = text.index("**Участники:**")
    idx_summary = text.index("**Резюме:**")
    idx_section1 = text.index("**1. Обсужденные")
    idx_section2 = text.index("**2. Открытые")
    idx_section3 = text.index("**3. Риски**")
    idx_author = text.index("**Составитель:**")
    assert idx_header < idx_participants < idx_summary < idx_section1 < idx_section2 < idx_section3 < idx_author
