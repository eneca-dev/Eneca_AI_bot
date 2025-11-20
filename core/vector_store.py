"""Vector store module for Supabase integration"""
from typing import List, Optional
from langchain_community.vectorstores import SupabaseVectorStore
from langchain_openai import OpenAIEmbeddings
from supabase import create_client, Client
from core.config import settings
from loguru import logger


class VectorStoreManager:
    """Manager for Supabase vector store operations"""

    def __init__(self):
        """Initialize vector store manager"""
        self.embeddings = None
        self.vector_store = None
        self.supabase_client = None
        self._initialize()

    def _initialize(self):
        """Initialize Supabase client and embeddings"""
        try:
            # Initialize OpenAI embeddings from configuration
            self.embeddings = OpenAIEmbeddings(
                model=settings.embedding_model,
                openai_api_key=settings.openai_api_key
            )
            logger.info(f"OpenAI embeddings initialized ({settings.embedding_model})")

            # Initialize Supabase client if credentials are available and valid
            if (settings.supabase_url and
                settings.supabase_key and
                not settings.supabase_url.startswith("your_") and
                not settings.supabase_key.startswith("your_")):

                try:
                    self.supabase_client = create_client(
                        supabase_url=settings.supabase_url,
                        supabase_key=settings.supabase_key
                    )
                    logger.info("Supabase client initialized")

                    # Initialize vector store
                    self.vector_store = SupabaseVectorStore(
                        client=self.supabase_client,
                        embedding=self.embeddings,
                        table_name="documents",  # Table name in Supabase
                        query_name="match_documents"  # Function name for similarity search
                    )
                    logger.info("Supabase vector store initialized")
                except Exception as supabase_error:
                    logger.error(f"Error connecting to Supabase: {supabase_error}")
                    logger.warning("Vector store will not be available.")
            else:
                logger.warning("Supabase credentials not provided or invalid. Vector store will not be available.")

        except Exception as e:
            logger.error(f"Error initializing embeddings: {e}")
            # Don't raise - allow system to continue without vector store

    def search(self, query: str, k: int = None) -> List[dict]:
        """
        Search for similar documents in vector store

        Args:
            query: Search query
            k: Number of results to return (defaults to config value)

        Returns:
            List of relevant documents with metadata
        """
        if not self.vector_store:
            logger.warning("Vector store not initialized. Cannot perform search.")
            return []

        # Use config default if not specified
        k = k or settings.vector_search_k

        try:
            logger.debug(f"Searching vector store for query: {query}")
            results = self.vector_store.similarity_search(query, k=k)

            documents = []
            for doc in results:
                # Ensure UTF-8 encoding for content
                content = doc.page_content
                if isinstance(content, bytes):
                    try:
                        content = content.decode('utf-8')
                    except UnicodeDecodeError:
                        try:
                            content = content.decode('windows-1251')
                            logger.warning(f"Document decoded using windows-1251 encoding")
                        except UnicodeDecodeError:
                            content = content.decode('utf-8', errors='replace')
                            logger.error(f"Document has encoding issues")

                documents.append({
                    "content": content,
                    "metadata": doc.metadata,
                    "relevance": "high"  # Will be calculated based on score in future
                })

            logger.info(f"Found {len(documents)} relevant documents")
            return documents

        except Exception as e:
            logger.error(f"Error searching vector store: {e}")
            return []

    def search_with_score(self, query: str, k: int = None, score_threshold: float = None) -> List[dict]:
        """
        Search for similar documents with relevance scores

        Args:
            query: Search query
            k: Number of results to return (defaults to config value)
            score_threshold: Minimum relevance score (defaults to config value)

        Returns:
            List of relevant documents with scores
        """
        if not self.vector_store:
            logger.warning("Vector store not initialized. Cannot perform search.")
            return []

        # Use config defaults if not specified
        k = k or settings.vector_search_k
        score_threshold = score_threshold or settings.similarity_threshold

        try:
            logger.debug(f"Searching vector store with scores for query: {query}")
            results = self.vector_store.similarity_search_with_relevance_scores(
                query, k=k, score_threshold=score_threshold
            )

            documents = []
            for doc, score in results:
                relevance = "high" if score >= 0.6 else "medium" if score >= 0.4 else "low"

                # Ensure UTF-8 encoding for content
                content = doc.page_content
                if isinstance(content, bytes):
                    try:
                        # Try UTF-8 first
                        content = content.decode('utf-8')
                    except UnicodeDecodeError:
                        # Fallback to Windows-1251 if UTF-8 fails
                        try:
                            content = content.decode('windows-1251')
                            logger.warning(f"Document decoded using windows-1251 encoding")
                        except UnicodeDecodeError:
                            # Last resort: decode with errors='replace'
                            content = content.decode('utf-8', errors='replace')
                            logger.error(f"Document has encoding issues, some characters may be replaced")

                documents.append({
                    "content": content,
                    "metadata": doc.metadata,
                    "score": score,
                    "relevance": relevance
                })

            logger.info(f"Found {len(documents)} documents above threshold {score_threshold}")
            return documents

        except Exception as e:
            logger.error(f"Error searching vector store with scores: {e}")
            return []

    def add_documents(self, texts: List[str], metadatas: Optional[List[dict]] = None) -> bool:
        """
        Add documents to vector store

        Args:
            texts: List of document texts
            metadatas: Optional list of metadata dicts for each document

        Returns:
            True if successful, False otherwise
        """
        if not self.vector_store:
            logger.error("Vector store not initialized. Cannot add documents.")
            return False

        try:
            logger.info(f"Adding {len(texts)} documents to vector store")
            self.vector_store.add_texts(texts=texts, metadatas=metadatas)
            logger.info("Documents added successfully")
            return True

        except Exception as e:
            logger.error(f"Error adding documents to vector store: {e}")
            return False

    def is_available(self) -> bool:
        """Check if vector store is available"""
        return self.vector_store is not None


# Global vector store instance
vector_store_manager = VectorStoreManager()
