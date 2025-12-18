"""
Cohere Reranker for improving RAG search quality

Reranks vector search results using Cohere's semantic reranking model.
This improves relevance by using cross-encoder scoring instead of cosine similarity.
"""
from typing import List, Dict, Any, Optional
from loguru import logger
from core.config import settings


class CohereReranker:
    """
    Cohere-based reranker for improving RAG search results.

    Uses Cohere's rerank API to re-score documents based on semantic
    relevance to the query, providing more accurate ranking than
    vector similarity alone.
    """

    def __init__(self):
        """Initialize Cohere reranker with settings from config"""
        self._client = None
        self._available = False
        self.model = settings.rerank_model
        self.enabled = settings.rerank_enabled

        self._initialize_client()

    def _initialize_client(self):
        """Initialize Cohere client if API key is available"""
        if not settings.cohere_api_key:
            logger.warning("COHERE_API_KEY not set - reranker disabled")
            self._available = False
            return

        if not self.enabled:
            logger.info("Reranker disabled via RERANK_ENABLED=false")
            self._available = False
            return

        try:
            import cohere
            self._client = cohere.Client(settings.cohere_api_key)
            self._available = True
            logger.info(f"Cohere reranker initialized with model: {self.model}")
        except ImportError:
            logger.error("cohere package not installed. Run: pip install cohere")
            self._available = False
        except Exception as e:
            logger.error(f"Failed to initialize Cohere client: {e}")
            self._available = False

    def is_available(self) -> bool:
        """Check if reranker is available and enabled"""
        return self._available and self._client is not None

    def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_n: int = None
    ) -> List[Dict[str, Any]]:
        """
        Rerank documents based on query relevance using Cohere.

        Args:
            query: User's search query
            documents: List of documents from vector search, each with 'content' and optional metadata
            top_n: Number of top results to return (defaults to config RERANK_TOP_N)

        Returns:
            Reranked list of documents with updated scores and relevance
        """
        if not self.is_available():
            logger.debug("Reranker not available, returning original documents")
            return documents[:top_n or settings.rerank_top_n]

        if not documents:
            return []

        top_n = top_n or settings.rerank_top_n

        try:
            # Extract document texts for Cohere API
            doc_texts = [doc.get("content", "") for doc in documents]

            # Call Cohere rerank API
            response = self._client.rerank(
                model=self.model,
                query=query,
                documents=doc_texts,
                top_n=min(top_n, len(documents)),
                return_documents=False  # We already have the documents
            )

            # Build reranked results
            reranked = []
            for result in response.results:
                original_doc = documents[result.index].copy()

                # Update score with Cohere relevance score
                original_doc["original_score"] = original_doc.get("score", 0)
                original_doc["score"] = result.relevance_score

                # Update relevance band based on Cohere score
                original_doc["relevance"] = self._get_relevance_band(result.relevance_score)
                original_doc["reranked"] = True

                reranked.append(original_doc)

            scores_str = ", ".join([f"{d['score']:.3f}" for d in reranked])
            logger.info(
                f"Reranked {len(documents)} documents -> top {len(reranked)} "
                f"(scores: [{scores_str}])"
            )

            return reranked

        except Exception as e:
            logger.error(f"Reranking failed: {e}, returning original documents")
            return documents[:top_n]

    def _get_relevance_band(self, score: float) -> str:
        """
        Convert Cohere relevance score to relevance band.

        Cohere scores are typically in range [0, 1] where:
        - >= 0.8: Very high relevance
        - >= 0.5: Good relevance
        - >= 0.3: Moderate relevance
        - < 0.3: Low relevance
        """
        if score >= 0.8:
            return "high"
        elif score >= 0.5:
            return "medium"
        elif score >= 0.3:
            return "low"
        else:
            return "very_low"


# Global singleton instance
reranker = CohereReranker()
