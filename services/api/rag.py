"""
RAG pipeline — Retrieval-Augmented Generation for economic queries.

Flow:
  1. Embed the user question with sentence-transformers
  2. Search Qdrant for the most semantically similar records
  3. Build context from retrieved payloads
  4. Send question + context to Ollama (qwen3.5) for answer generation
  5. Return answer + sources
"""
import os
import logging

from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from openai import OpenAI

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
COLLECTION  = "economic_indicators"
MODEL_NAME  = "all-MiniLM-L6-v2"
TOP_K       = 10


# ── Singletons (loaded once when the API starts) ─────────────────────────────
_embedding_model = None
_qdrant_client   = None
_llm_client      = None


def get_embedding_model() -> SentenceTransformer:
    global _embedding_model
    if _embedding_model is None:
        log.info("Loading embedding model...")
        _embedding_model = SentenceTransformer(MODEL_NAME)
    return _embedding_model


def get_qdrant() -> QdrantClient:
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(
            host=os.getenv("QDRANT_HOST", "qdrant"),
            port=int(os.getenv("QDRANT_PORT", 6333)),
        )
    return _qdrant_client


def get_llm_client() -> OpenAI:
    global _llm_client
    if _llm_client is None:
        _llm_client = OpenAI(
            base_url=os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434/v1"),
            api_key="ollama",
        )
    return _llm_client


# ── RAG pipeline ──────────────────────────────────────────────────────────────
def rag_query(question: str, region: str = None, top_k: int = TOP_K) -> dict:
    """
    Answer a natural language question about economic data.

    Args:
        question: Natural language question from the user
        region:   Optional World Bank region to filter results
        top_k:    Number of records to retrieve from Qdrant

    Returns:
        dict with 'answer', 'sources', and 'context_records'
    """
    # Step 1 — embed the question
    model = get_embedding_model()
    query_vector = model.encode(question).tolist()

    # Step 2 — search Qdrant
    search_filter = None
    if region:
        search_filter = Filter(
            must=[FieldCondition(
                key="region",
                match=MatchValue(value=region)
            )]
        )

    results = get_qdrant().query_points(
        collection_name=COLLECTION,
        query=query_vector,
        limit=top_k,
        query_filter=search_filter,
        with_payload=True,
    ).points


    if not results:
        return {
            "answer": "No relevant economic data found for your question.",
            "sources": [],
            "context_records": 0,
        }

    # Step 3 — build context from retrieved payloads
    context_parts = []
    sources = []

    for hit in results:
        payload = hit.payload
        context_parts.append(payload.get("text", ""))
        sources.append({
            "country": payload.get("country_name"),
            "year":    payload.get("year"),
            "score":   round(hit.score, 4),
        })

    context = "\n\n".join(context_parts)

    # Step 4 — generate answer with Ollama
    prompt = f"""You are an economic research assistant. Answer the question using ONLY the data provided below. Do not use any outside knowledge. Be specific — cite country names and years from the data. Keep your answer concise and factual. Do not show your thinking process.

DATA:
{context}

QUESTION: {question}

ANSWER:"""

    response = get_llm_client().chat.completions.create(
        model=os.getenv("OLLAMA_MODEL", "qwen3.5:latest"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )

    raw_answer = response.choices[0].message.content
    log.info(f"Raw LLM response: {raw_answer[:200]}")
    
    # Strip Qwen3 thinking blocks if present
    if "<think>" in raw_answer and "</think>" in raw_answer:
        answer = raw_answer.split("</think>")[-1].strip()
    else:
        answer = raw_answer.strip()

    return {
        "answer":          answer,
        "sources":         sources,
        "context_records": len(results),
    }
