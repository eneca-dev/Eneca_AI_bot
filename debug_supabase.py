"""Debug script to investigate Supabase documents table"""
from core.vector_store import vector_store_manager
from supabase import create_client
from core.config import settings
from loguru import logger

print("=" * 80)
print("Supabase Documents Table Debug")
print("=" * 80)

# Check if vector store is available
print(f"\n[CHECK] Vector store available: {vector_store_manager.is_available()}")

if not vector_store_manager.is_available():
    print("[ERROR] Vector store not available. Cannot debug.")
    exit(1)

# Connect to Supabase directly to check table contents
print("\n[INFO] Connecting to Supabase to check table contents...")
try:
    supabase = create_client(settings.supabase_url, settings.supabase_key)

    # Query documents table
    print("[INFO] Querying documents table...")
    response = supabase.table("documents").select("id, content, metadata").limit(10).execute()

    if response.data:
        print(f"\n[SUCCESS] Found {len(response.data)} documents in table:")
        print("-" * 80)
        for i, doc in enumerate(response.data, 1):
            print(f"\nDocument {i}:")
            print(f"  ID: {doc.get('id')}")
            print(f"  Content preview: {doc.get('content', '')[:200]}...")
            print(f"  Metadata: {doc.get('metadata')}")
        print("-" * 80)
    else:
        print("\n[WARNING] No documents found in table!")
        print("[INFO] You may need to add documents to the database first.")

except Exception as e:
    print(f"[ERROR] Failed to query Supabase: {e}")
    exit(1)

# Test search with different thresholds
print("\n" + "=" * 80)
print("Testing Search with Different Relevance Thresholds")
print("=" * 80)

test_query = "Как создать новый проект?"
print(f"\nTest Query: {test_query}")

thresholds = [0.5, 0.6, 0.7, 0.8]

for threshold in thresholds:
    print(f"\n[TEST] Threshold: {threshold}")
    print("-" * 80)

    try:
        results = vector_store_manager.search_with_score(
            query=test_query,
            k=3,
            score_threshold=threshold
        )

        if results:
            print(f"[SUCCESS] Found {len(results)} results:")
            for i, result in enumerate(results, 1):
                print(f"\n  Result {i}:")
                print(f"    Score: {result['score']:.4f}")
                print(f"    Relevance: {result['relevance']}")
                print(f"    Content: {result['content'][:150]}...")
        else:
            print(f"[INFO] No results above threshold {threshold}")

    except Exception as e:
        print(f"[ERROR] Search failed: {e}")

# Test with basic search (no threshold)
print("\n" + "=" * 80)
print("Testing Basic Search (No Threshold)")
print("=" * 80)

try:
    results = vector_store_manager.search(query=test_query, k=5)

    if results:
        print(f"\n[SUCCESS] Found {len(results)} results:")
        for i, result in enumerate(results, 1):
            print(f"\n  Result {i}:")
            print(f"    Content: {result['content'][:200]}...")
            print(f"    Metadata: {result['metadata']}")
    else:
        print("[INFO] No results found with basic search")

except Exception as e:
    print(f"[ERROR] Basic search failed: {e}")

# Test with similarity search with score (no threshold parameter)
print("\n" + "=" * 80)
print("Testing Similarity Search with Actual Scores")
print("=" * 80)

try:
    # Use the underlying LangChain method to get actual scores
    from langchain_core.documents import Document

    print(f"\nTest Query: {test_query}")
    results_with_scores = vector_store_manager.vector_store.similarity_search_with_relevance_scores(
        query=test_query,
        k=5,
        score_threshold=0.0  # Set to 0 to get all results with scores
    )

    if results_with_scores:
        print(f"\n[SUCCESS] Found {len(results_with_scores)} results with scores:")
        for i, (doc, score) in enumerate(results_with_scores, 1):
            print(f"\n  Result {i}:")
            print(f"    Similarity Score: {score:.4f}")
            print(f"    Content: {doc.page_content[:200]}...")
            print(f"    Metadata: {doc.metadata}")
    else:
        print("[INFO] No results found")

except Exception as e:
    print(f"[ERROR] Similarity search with scores failed: {e}")

print("\n" + "=" * 80)
print("Debug Complete")
print("=" * 80)
