"""
RAG Document Ingestion — Load project docs into ChromaDB vector store.
=====================================================================
Reads all .md files from the project root and indexes them into a local
vector database. The MCP server can then search these docs to answer
"how did we fix X?" type questions.

Usage:
  cd mcp-server/rag
  python ingest.py

Re-run whenever docs are updated to refresh the index.
"""

import os
import glob
import chromadb
from chromadb.utils import embedding_functions

# Configuration
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
CHROMA_DIR = os.path.join(os.path.dirname(__file__), "chroma_db")
COLLECTION_NAME = "devops_docs"

# Document paths to ingest (relative to project root)
DOC_PATTERNS = [
    "*.md",                          # Root-level docs (README, DEPLOYMENT-GUIDE, etc.)
    "mcp-server/README.md",          # MCP server docs
    "ansible/README.md",             # Ansible docs
    "kubernetes/**/*.yaml",          # K8s manifests (for context)
    "charts/microservice/*.yaml",    # Helm values
    "scripts/*.sh",                  # Install scripts
    "Jenkinsfile",                   # Pipeline
]


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> list:
    """Split text into overlapping chunks for better retrieval."""
    chunks = []
    lines = text.split("\n")
    current_chunk = []
    current_size = 0

    for line in lines:
        current_chunk.append(line)
        current_size += len(line)

        if current_size >= chunk_size:
            chunks.append("\n".join(current_chunk))
            # Keep overlap
            overlap_lines = current_chunk[-(overlap // 50):]
            current_chunk = overlap_lines
            current_size = sum(len(l) for l in current_chunk)

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    return chunks


def load_documents() -> list:
    """Load all project documents and split into chunks."""
    documents = []
    metadatas = []
    ids = []
    doc_id = 0

    for pattern in DOC_PATTERNS:
        full_pattern = os.path.join(PROJECT_ROOT, pattern)
        files = glob.glob(full_pattern, recursive=True)

        for filepath in files:
            # Skip .terraform and .git directories
            if ".terraform" in filepath or ".git" in filepath:
                continue

            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                if not content.strip():
                    continue

                # Get relative path for metadata
                rel_path = os.path.relpath(filepath, PROJECT_ROOT)

                # Chunk the document
                chunks = chunk_text(content)

                for i, chunk in enumerate(chunks):
                    documents.append(chunk)
                    metadatas.append({
                        "source": rel_path,
                        "chunk": i,
                        "total_chunks": len(chunks),
                    })
                    ids.append(f"doc_{doc_id}")
                    doc_id += 1

                print(f"  ✅ {rel_path} → {len(chunks)} chunks")

            except Exception as e:
                print(f"  ❌ {filepath}: {e}")

    return documents, metadatas, ids


def ingest():
    """Main ingestion function — loads docs into ChromaDB."""
    print("=" * 50)
    print("RAG Document Ingestion")
    print("=" * 50)
    print(f"Project root: {PROJECT_ROOT}")
    print(f"ChromaDB path: {CHROMA_DIR}")
    print()

    # Initialize ChromaDB
    client = chromadb.PersistentClient(path=CHROMA_DIR)

    # Use a lightweight embedding model (runs locally, no API key needed)
    embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )

    # Delete existing collection if it exists (fresh ingest)
    try:
        client.delete_collection(COLLECTION_NAME)
        print("🗑️  Deleted existing collection (re-indexing)")
    except Exception:
        pass

    # Create collection
    collection = client.create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_fn,
        metadata={"description": "DevOps project documentation for RAG queries"}
    )

    # Load and ingest documents
    print("\nLoading documents...")
    documents, metadatas, ids = load_documents()

    if not documents:
        print("❌ No documents found!")
        return

    # Add to ChromaDB (batch to avoid memory issues)
    batch_size = 100
    for i in range(0, len(documents), batch_size):
        batch_docs = documents[i:i + batch_size]
        batch_meta = metadatas[i:i + batch_size]
        batch_ids = ids[i:i + batch_size]
        collection.add(documents=batch_docs, metadatas=batch_meta, ids=batch_ids)

    print(f"\n✅ Ingested {len(documents)} chunks from {len(set(m['source'] for m in metadatas))} files")
    print(f"   Collection: {COLLECTION_NAME}")
    print(f"   Stored at: {CHROMA_DIR}")


if __name__ == "__main__":
    ingest()
