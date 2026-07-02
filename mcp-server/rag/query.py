"""
RAG Query Engine — Search project docs and return relevant answers.
===================================================================
Queries the ChromaDB vector store to find relevant documentation
chunks based on natural language questions.

Used by the MCP server to answer "how did we fix X?" type questions.

Usage (standalone test):
  python query.py "how to fix Jenkins Init:0/2"
"""

import os
import sys
import chromadb
from chromadb.utils import embedding_functions

# Configuration
CHROMA_DIR = os.path.join(os.path.dirname(__file__), "chroma_db")
COLLECTION_NAME = "devops_docs"


def get_collection():
    """Get the ChromaDB collection (creates client on demand)."""
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    return client.get_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_fn
    )


def search_docs(query: str, n_results: int = 5) -> str:
    """
    Search project documentation using semantic similarity.
    
    Args:
        query: Natural language question (e.g., "how to fix pod CrashLoopBackOff")
        n_results: Number of relevant chunks to return (default: 5)
    
    Returns:
        Formatted string with relevant document sections and their sources.
    """
    try:
        collection = get_collection()
    except Exception as e:
        return f"❌ RAG database not found. Run 'python rag/ingest.py' first.\nError: {e}"

    # Query the vector store
    results = collection.query(
        query_texts=[query],
        n_results=n_results,
        include=["documents", "metadatas", "distances"]
    )

    if not results["documents"][0]:
        return "No relevant documentation found for this query."

    # Format results
    output = []
    output.append(f"📚 Found {len(results['documents'][0])} relevant sections:\n")

    for i, (doc, meta, distance) in enumerate(zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0]
    )):
        relevance = max(0, round((1 - distance) * 100, 1))
        source = meta.get("source", "unknown")
        chunk_num = meta.get("chunk", 0)

        output.append(f"--- [{i+1}] Source: {source} (chunk {chunk_num}, relevance: {relevance}%) ---")
        # Trim long chunks for readability
        if len(doc) > 800:
            doc = doc[:800] + "\n... [truncated]"
        output.append(doc)
        output.append("")

    return "\n".join(output)


def search_docs_with_context(query: str) -> dict:
    """
    Search and return structured results (for programmatic use).
    
    Returns dict with:
        - answer_context: combined relevant text
        - sources: list of source files
        - relevance_scores: list of similarity percentages
    """
    try:
        collection = get_collection()
    except Exception:
        return {"answer_context": "", "sources": [], "relevance_scores": []}

    results = collection.query(
        query_texts=[query],
        n_results=5,
        include=["documents", "metadatas", "distances"]
    )

    if not results["documents"][0]:
        return {"answer_context": "", "sources": [], "relevance_scores": []}

    context = "\n\n".join(results["documents"][0])
    sources = [m.get("source", "unknown") for m in results["metadatas"][0]]
    scores = [max(0, round((1 - d) * 100, 1)) for d in results["distances"][0]]

    return {
        "answer_context": context,
        "sources": list(set(sources)),
        "relevance_scores": scores,
    }


# CLI test
if __name__ == "__main__":
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
    else:
        query = "how to fix Jenkins pod stuck in Init"

    print(f"Query: {query}\n")
    print(search_docs(query))
