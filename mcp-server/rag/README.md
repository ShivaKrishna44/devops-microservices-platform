# RAG Module — AI-Powered Documentation Search

Adds semantic search over your project documentation to the MCP server.
The AI agent can now answer "how did we fix X?" by searching your actual runbooks and troubleshooting notes.

---

## How It Works

```
1. ingest.py reads all .md, .yaml, .sh files from your project
2. Splits them into chunks (500 chars with overlap)
3. Generates embeddings using SentenceTransformer (runs locally, no API key)
4. Stores in ChromaDB (local vector database, no server needed)
5. query.py searches by semantic similarity when agent asks a question
```

**Architecture:**
```
User: "How did we fix Jenkins Init:0/2?"
    ↓
MCP Server → search_runbook("Jenkins Init:0/2")
    ↓
RAG query.py → ChromaDB semantic search
    ↓
Returns: relevant chunks from TROUBLESHOOTING.md, DEPLOYMENT-GUIDE.md
    ↓
Agent: "The fix was to create jenkins-admin-secret before Helm install..."
```

---

## Setup

```bash
cd mcp-server

# Install dependencies
pip install -r requirements.txt

# Index your documents (run once, re-run when docs change)
python rag/ingest.py
```

**Output:**
```
RAG Document Ingestion
==================================================
  ✅ DEPLOYMENT-GUIDE.md → 45 chunks
  ✅ TROUBLESHOOTING.md → 22 chunks
  ✅ README.md → 8 chunks
  ✅ Jenkinsfile → 5 chunks
  ✅ kubernetes/jenkins/jenkins-values.yaml → 3 chunks
  ...

✅ Ingested 120 chunks from 15 files
```

---

## MCP Tools Added

| Tool | Purpose | Example Query |
|---|---|---|
| `search_runbook` | General doc search | "how to set up monitoring" |
| `search_troubleshooting` | Find fixes for errors | "ImagePullBackOff ECR" |
| `search_deployment_steps` | Find setup instructions | "Jenkins installation" |

---

## Test Standalone

```bash
# Search for a topic
python rag/query.py "how to fix pod CrashLoopBackOff"

# Search for an error
python rag/query.py "MountVolume.SetUp failed secret not found"

# Search for setup steps
python rag/query.py "install ArgoCD on EKS"
```

---

## Re-Index (when docs change)

```bash
python rag/ingest.py
# Deletes old index and creates fresh one
```

---

## Key Points for Interview

> "I added RAG to my MCP monitoring server. It combines live cluster monitoring (kubectl, Prometheus) with historical knowledge (documentation search). When the agent detects a failing pod, it can also search our troubleshooting docs to suggest a fix based on how we solved similar issues before. The vector database runs locally using ChromaDB — no external API needed. Embeddings are generated with SentenceTransformer (all-MiniLM-L6-v2), which is a lightweight model that runs on CPU."
