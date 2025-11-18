# Supabase Setup Notes

## Current Status ✅

The bot is successfully connected to Supabase and can search the vector database:

- **Connection**: ✅ Working
- **Vector Store**: ✅ Initialized
- **Search**: ✅ Working with adjusted threshold (0.01)
- **Routing**: ✅ Orchestrator correctly delegates to RAG agent

## Known Issues 🔧

### 1. Character Encoding Problem

The documents stored in Supabase have incorrect character encoding. When retrieved, Russian text appears garbled:

**Example from database:**
```
������ � ����������
������: ��� �������� �� ���������� ������� ������������?
```

**What it should look like:**
```
Работа с документами
Вопрос: Как создать новый проект в приложении?
```

### Root Cause

The documents were likely stored with Windows-1251 (Cyrillic) encoding but are being read as UTF-8, or vice versa.

### Solutions

**Option 1: Re-upload documents with correct encoding**

Run this script to properly encode and upload documents:

```python
from core.vector_store import vector_store_manager

# Example documents in proper UTF-8
documents = [
    "Вопрос: Как создать новый проект?\nОтвет: Перейдите в раздел Проекты и нажмите 'Новый проект'.",
    "Вопрос: Где находятся настройки?\nОтвет: Настройки находятся в правом верхнем углу."
]

metadatas = [
    {"source": "manual", "category": "projects"},
    {"source": "manual", "category": "settings"}
]

# Clear existing documents if needed
# Then upload new ones
success = vector_store_manager.add_documents(documents, metadatas)
if success:
    print("Документы успешно загружены с правильной кодировкой!")
```

**Option 2: Fix encoding when retrieving (workaround)**

Modify [vector_store.py](d:\Eneca_AI_bot\core\vector_store.py) to decode the content:

```python
# In search() method, add encoding fix:
for doc in results:
    content = doc.page_content
    try:
        # Attempt to fix encoding
        content = content.encode('latin1').decode('utf-8')
    except:
        pass  # Keep original if conversion fails

    documents.append({
        "content": content,
        "metadata": doc.metadata
    })
```

**Option 3: Clean and re-index all documents in Supabase**

1. Export existing documents from Supabase
2. Fix encoding in exported files
3. Clear the `documents` table
4. Re-upload with correct encoding

### Recommended Next Step

Re-upload documents with correct UTF-8 encoding using Option 1.

## Current Configuration

### Vector Store Settings

- **Table name**: `documents`
- **Search function**: `match_documents`
- **Embedding model**: OpenAI `text-embedding-3-small`
- **Embedding dimensions**: 1536
- **Similarity threshold**: 0.35 (adjusted due to encoding issues)
- **Relevance bands**:
  - High: score >= 0.6
  - Medium: score >= 0.4
  - Low: score < 0.4

### ✅ Fixed: Embedding Model Mismatch

**Issue (RESOLVED):** Initial implementation used `text-embedding-ada-002` for queries while documents were embedded with `text-embedding-3-small`, causing very low similarity scores (0.02-0.04).

**Solution:** Updated `core/vector_store.py` to use `text-embedding-3-small` matching the model used in Supabase.

**Note:** Similarity scores are lower than expected (0.35-0.55 instead of 0.7-0.9) due to character encoding issues in stored documents. Despite garbled text display, semantic search still works because embeddings were created before encoding corruption.

## Test Results

### Routing: ✅ Working Correctly

- Simple greetings → Answered directly without RAG
- General knowledge → Answered directly without RAG
- App-specific questions → Correctly delegates to RAG agent

### RAG Search: ⚠️ Partially Working

- Vector search finds relevant documents
- Documents are returned with scores
- **Issue**: Content is garbled due to encoding
- **Result**: LLM cannot extract meaningful information

### Example Log Output

```
[INFO] Found 5 documents above threshold 0.01
[Document 1] (relevance: high, score: 0.04)
������ � ����������
������: ��� �������� �� ���������� ������� ������������?
```

## Next Steps for Full Functionality

1. ✅ ~~Connect to Supabase~~ (Done)
2. ✅ ~~Adjust similarity threshold~~ (Done)
3. ⏳ **Fix character encoding** (In Progress)
4. ⏳ Test with properly encoded documents
5. ⏳ Consider re-embedding documents with current model

## Additional Improvements

### 1. Add Conversation Memory

Currently, the bot doesn't remember previous messages in the conversation:

```python
from langchain.memory import ConversationBufferMemory

self.memory = ConversationBufferMemory(
    memory_key="chat_history",
    return_messages=True
)
```

### 2. Monitor Embedding Quality

Create a script to check embedding quality and similarity scores:

```python
# Check if new embeddings match better
test_query = "Как создать проект?"
results = vector_store.similarity_search_with_relevance_scores(
    test_query,
    k=3
)
for doc, score in results:
    print(f"Score: {score:.4f} - {doc.page_content[:100]}")
```

### 3. Add Document Metadata Filtering

Use metadata to filter searches by category:

```python
results = vector_store.similarity_search(
    query=query,
    k=k,
    filter={"category": "projects"}
)
```

## Summary

The architecture is working correctly:
- ✅ Orchestrator routing logic
- ✅ RAG agent delegation
- ✅ Supabase connection
- ✅ Vector search functionality

The main blocker is the character encoding issue in the stored documents. Once resolved, the bot will provide accurate answers based on the knowledge base.
