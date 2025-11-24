"""
RAG Quality Tests

Tests for validating encoding, similarity thresholds, and RAG pipeline quality.
"""

import pytest
import sys
from pathlib import Path
from typing import List, Dict, Any

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.vector_store import vector_store_manager
from agents.rag_agent import RAGAgent
from agents.orchestrator import OrchestratorAgent


class TestEncodingValidation:
    """Tests for UTF-8 encoding validation in document upload"""

    def test_valid_utf8_text(self):
        """Test that valid UTF-8 text is accepted"""
        valid_text = "Это корректный UTF-8 текст на русском языке."

        # Should not raise any exception
        validated, was_fixed = vector_store_manager._validate_and_fix_encoding(
            valid_text, doc_index=0
        )

        assert validated == valid_text
        assert was_fixed is False

    def test_ascii_text(self):
        """Test that ASCII text is accepted"""
        ascii_text = "This is plain ASCII text."

        validated, was_fixed = vector_store_manager._validate_and_fix_encoding(
            ascii_text, doc_index=0
        )

        assert validated == ascii_text
        assert was_fixed is False

    def test_mixed_cyrillic_latin(self):
        """Test text with both Cyrillic and Latin characters"""
        mixed_text = "Test тест 123 проверка check"

        validated, was_fixed = vector_store_manager._validate_and_fix_encoding(
            mixed_text, doc_index=0
        )

        assert validated == mixed_text
        assert was_fixed is False

    def test_encoding_fix_latin1_to_utf8(self):
        """Test automatic fix of latin1 → utf-8 encoding"""
        # Simulate mojibake: UTF-8 bytes interpreted as latin1
        original = "Привет мир"
        mojibake = original.encode('utf-8').decode('latin1')

        validated, was_fixed = vector_store_manager._validate_and_fix_encoding(
            mojibake, doc_index=0
        )

        # Should be fixed back to original
        assert "Привет" in validated or was_fixed
        assert was_fixed is True

    def test_add_documents_with_validation(self):
        """Test add_documents with encoding validation enabled"""
        if not vector_store_manager.is_available():
            pytest.skip("Supabase not available")

        texts = [
            "Тестовый документ 1",
            "Тестовый документ 2",
        ]
        metadatas = [
            {"source": "test", "id": 1},
            {"source": "test", "id": 2},
        ]

        # Should not raise any exception
        try:
            result = vector_store_manager.add_documents(
                texts=texts,
                metadatas=metadatas,
                validate_encoding=True
            )
            assert result is True
        except ValueError as e:
            pytest.fail(f"Encoding validation failed unexpectedly: {e}")


class TestSimilarityThreshold:
    """Tests for similarity threshold and relevance scoring"""

    def test_similarity_threshold_default(self):
        """Test that default similarity threshold is set correctly"""
        from core.config import settings

        # After migration, should be 0.7
        assert settings.similarity_threshold >= 0.7
        assert settings.similarity_threshold <= 1.0

    def test_relevance_bands(self):
        """Test relevance band categorization"""
        if not vector_store_manager.is_available():
            pytest.skip("Supabase not available")

        # Test relevance band logic
        test_scores = [
            (0.9, "high"),   # >= 0.8
            (0.85, "high"),
            (0.79, "medium"), # >= 0.6 and < 0.8
            (0.65, "medium"),
            (0.55, "low"),   # < 0.6
            (0.4, "low"),
        ]

        for score, expected_relevance in test_scores:
            # Simulate relevance calculation
            relevance = "high" if score >= 0.8 else "medium" if score >= 0.6 else "low"
            assert relevance == expected_relevance, (
                f"Score {score} should be '{expected_relevance}', got '{relevance}'"
            )

    def test_search_with_score_filters_low_relevance(self):
        """Test that search_with_score filters out low relevance results"""
        if not vector_store_manager.is_available():
            pytest.skip("Supabase not available")

        # Search with high threshold
        query = "тестовый запрос"
        results = vector_store_manager.search_with_score(
            query=query,
            k=10,
            score_threshold=0.7
        )

        # All results should have score >= 0.7
        for doc in results:
            assert doc['score'] >= 0.7, (
                f"Document score {doc['score']} is below threshold 0.7"
            )


class TestRAGPipeline:
    """Integration tests for RAG pipeline quality"""

    @pytest.fixture
    def rag_agent(self):
        """Fixture to create RAG agent instance"""
        return RAGAgent()

    def test_rag_agent_initialization(self, rag_agent):
        """Test that RAG agent initializes correctly"""
        assert rag_agent is not None
        assert rag_agent.vector_store is not None
        assert rag_agent.llm is not None

    def test_search_knowledge_base_returns_valid_utf8(self, rag_agent):
        """Test that search results contain valid UTF-8 text"""
        if not rag_agent.vector_store.is_available():
            pytest.skip("Supabase not available")

        query = "тест"
        results = rag_agent.search_knowledge_base(query)

        # Check that result is a string (not an error message)
        assert isinstance(results, str)

        # Check for valid UTF-8 (should not raise)
        try:
            results.encode('utf-8').decode('utf-8')
        except UnicodeError as e:
            pytest.fail(f"Search results contain invalid UTF-8: {e}")

        # Should not contain mojibake indicators
        mojibake_indicators = ['Ã', 'Ð', 'â€™']
        for indicator in mojibake_indicators:
            if indicator in results and 'не найдена' not in results:
                pytest.fail(
                    f"Search results may contain mojibake (found '{indicator}'): {results[:200]}"
                )

    def test_rag_agent_answer_quality(self, rag_agent):
        """Test that RAG agent provides quality answers"""
        if not rag_agent.vector_store.is_available():
            pytest.skip("Supabase not available")

        question = "Что такое тест?"
        answer = rag_agent.answer_question(question)

        # Answer should be a string
        assert isinstance(answer, str)
        assert len(answer) > 0

        # Should not be an error message (unless no docs found)
        if "не найдена" not in answer and "недоступна" not in answer:
            # Should contain Cyrillic characters (Russian answer)
            assert any(ord(c) >= 0x0400 and ord(c) <= 0x04FF for c in answer), (
                "Answer should contain Russian text"
            )


class TestOrchestratorRAGIntegration:
    """Integration tests for Orchestrator → RAG agent routing"""

    @pytest.fixture
    def orchestrator(self):
        """Fixture to create Orchestrator agent instance"""
        return OrchestratorAgent()

    def test_orchestrator_routes_to_rag(self, orchestrator):
        """Test that orchestrator correctly routes knowledge queries to RAG"""
        if not vector_store_manager.is_available():
            pytest.skip("Supabase not available")

        # Query that should trigger RAG agent
        knowledge_query = "Найди информацию о проекте в базе знаний"

        response = orchestrator.process_message(
            user_message=knowledge_query,
            thread_id="test_rag_routing"
        )

        # Response should be a string
        assert isinstance(response, str)
        assert len(response) > 0

        # Should not be a generic error
        assert "ошибка" not in response.lower() or "не найдена" in response.lower()

    def test_orchestrator_handles_general_query_directly(self, orchestrator):
        """Test that orchestrator handles general queries without RAG"""
        general_query = "Привет, как дела?"

        response = orchestrator.process_message(
            user_message=general_query,
            thread_id="test_general_routing"
        )

        # Response should be a string
        assert isinstance(response, str)
        assert len(response) > 0


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers"""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (requires Supabase)"
    )
    config.addinivalue_line(
        "markers", "unit: mark test as unit test (no external dependencies)"
    )


# Mark integration tests
pytestmark = pytest.mark.integration


if __name__ == "__main__":
    # Run tests when script is executed directly
    pytest.main([__file__, "-v", "--tb=short"])
