# MCP + RAG Setup Guide — AI-Powered DevOps Monitoring Agent

Complete step-by-step guide to set up the MCP monitoring server with RAG (documentation search).

---

## What This Does

```
┌─────────────────────────────────────────────────────────────────┐
│                    MCP + RAG Architecture                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  You ask: "Is anything broken? How did we fix this last time?"    │
│                     ↓                                             │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │              MCP Server (mcp_server.py)                  │     │
│  │                                                         │     │
│  │  LIVE TOOLS (35+):          RAG TOOLS (3):              │     │
│  │  ├── kubectl ops            ├── search_runbook          │     │
│  │  ├── prometheus queries     ├── search_troubleshooting  │     │
│  │  ├── github operations      └── search_deployment_steps │     │
│  │  └── aws cli                                            │     │
│  └────────────┬──────────────────────────┬─────────────────┘     │
│               ↓                          ↓                        │
│  ┌────────────────────┐    ┌──────────────────────────┐          │
│  │  Live Cluster      │    │  ChromaDB Vector Store    │          │
│  │  (EKS, Prometheus) │    │  (Your docs indexed)     │          │
│  └────────────────────┘    └──────────────────────────┘          │
│                                                                   │
│  Result: "2 pods failing. ImagePullBackOff on order-service.      │
│           Based on our docs, this was fixed before by updating    │
│           the image tag in values-order.yaml to 'latest12'."      │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

| Requirement | Check Command | Install If Missing |
|---|---|---|
| Python 3.9+ | `python --version` | [python.org](https://www.python.org/downloads/) |
| pip | `pip --version` | Comes with Python |
| kubectl configured | `kubectl get nodes` | `aws eks update-kubeconfig --name expense-dev` |
| AWS CLI configured | `aws sts get-caller-identity` | `aws configure` |

---

## Step 1: Install Dependencies

```bash
cd mcp-server
pip install -r requirements.txt
```

**What gets installed:**
| Package | Purpose |
|---|---|
| `fastmcp` | MCP server framework |
| `requests` | HTTP calls to Prometheus |
| `boto3` | AWS SDK for Python |
| `PyGithub` | GitHub API access |
| `chromadb` | Local vector database (RAG) |
| `sentence-transformers` | Embedding model (runs locally, no API key) |

⚠️ First install of `sentence-transformers` downloads a ~90MB model. This is one-time only.

---

## Step 2: Set Environment Variables

```bash
# Required for GitHub tools
export GITHUB_TOKEN="ghp_your_github_personal_access_token"

# Optional (defaults shown)
export AWS_REGION="us-east-1"
export PROMETHEUS_URL="http://localhost:9090"
export KUBECTL_PATH="kubectl"
export GITHUB_OWNER="ShivaKrishna44"
```

**On Windows (PowerShell):**
```powershell
$env:GITHUB_TOKEN = "ghp_your_token"
$env:AWS_REGION = "us-east-1"
```

**On Windows (CMD):**
```cmd
set GITHUB_TOKEN=ghp_your_token
set AWS_REGION=us-east-1
```

---

## Step 3: Index Your Documentation (RAG Setup)

```bash
cd mcp-server
python rag/ingest.py
```

**Expected output:**
```
==================================================
RAG Document Ingestion
==================================================
Project root: C:\Devops\Repository\MCP based devops
ChromaDB path: C:\Devops\Repository\MCP based devops\mcp-server\rag\chroma_db

Loading documents...
  ✅ README.md → 8 chunks
  ✅ Jenkinsfile → 5 chunks
  ✅ ansible/README.md → 6 chunks
  ✅ kubernetes/jenkins/jenkins-values.yaml → 3 chunks
  ✅ kubernetes/ingress/app-ingress.yaml → 2 chunks
  ✅ scripts/01-install-tools.sh → 4 chunks
  ✅ scripts/03-install-jenkins.sh → 5 chunks
  ...

✅ Ingested 85 chunks from 18 files
   Collection: devops_docs
   Stored at: mcp-server/rag/chroma_db
```

**What gets indexed:**
- All `.md` files (README, deployment guides)
- Kubernetes YAML manifests
- Helm chart values
- Shell scripts
- Jenkinsfile

---

## Step 4: Test RAG Standalone (Optional)

```bash
cd mcp-server

# Test a search query
python rag/query.py "how to fix Jenkins Init:0/2"
```

**Expected output:**
```
Query: how to fix Jenkins Init:0/2

📚 Found 5 relevant sections:

--- [1] Source: scripts/03-install-jenkins.sh (chunk 2, relevance: 87.3%) ---
# Create Jenkins admin secret FIRST
kubectl create secret generic jenkins-admin-secret ...

--- [2] Source: kubernetes/jenkins/jenkins-values.yaml (chunk 0, relevance: 82.1%) ---
controller:
  admin:
    existingSecret: jenkins-admin-secret
...
```

---

## Step 5: Start the MCP Server

```bash
cd mcp-server
python mcp_server.py
```

**Expected output:**
```
Starting DevOps Platform Monitor MCP Server...
  kubectl: kubectl
  Prometheus: http://localhost:9090
  AWS Region: us-east-1
  GitHub Owner: ShivaKrishna44
  GitHub Token: configured

Tools: kubectl, prometheus, github, aws, rag
RAG: search_runbook, search_troubleshooting, search_deployment_steps
```

Server is now running and ready for tool calls.

---

## Step 6: Connect to AI Agent (Kiro)

Add to `.kiro/settings/mcp.json`:

```json
{
  "mcpServers": {
    "k8s-monitor": {
      "command": "python",
      "args": ["mcp-server/mcp_server.py"],
      "env": {
        "GITHUB_TOKEN": "ghp_your_token",
        "AWS_REGION": "us-east-1",
        "PROMETHEUS_URL": "http://localhost:9090"
      },
      "disabled": false
    }
  }
}
```

Now in Kiro chat, you can ask:
- "Is anything broken in the cluster?" → calls live kubectl tools
- "How did we fix the Jenkins Init issue?" → searches your docs via RAG
- "Show me deployment steps for ArgoCD" → finds relevant sections

---

## Step 7: Enable Prometheus Queries (Optional)

For Prometheus metrics to work, port-forward in a separate terminal:

```bash
kubectl port-forward svc/monitoring-kube-prometheus-prometheus -n monitoring 9090:9090
```

Keep this running while using the MCP server.

---

## All Available Tools (38 total)

### Live Kubernetes Tools (15)
| Tool | What It Does |
|---|---|
| `list_pods(namespace)` | List pods in a namespace |
| `list_all_pods()` | All pods across cluster |
| `describe_pod(pod, namespace)` | Detailed pod info + events |
| `get_pod_logs(pod, namespace, lines)` | Pod log output |
| `get_pod_events(pod, namespace)` | Events for a specific pod |
| `check_failing_pods()` | Find unhealthy pods |
| `check_high_restarts(threshold)` | Pods restarting too often |
| `check_pending_pods()` | Pods stuck in Pending |
| `get_node_status()` | Node health |
| `get_node_resource_usage()` | CPU/memory per node |
| `check_high_cpu()` | CPU-heavy pods |
| `check_high_memory()` | Memory-heavy pods |
| `get_deployments(namespace)` | Deployment status |
| `get_all_deployments()` | All deployments |
| `check_rollout_status(deployment)` | Is rollout stuck? |

### Ingress & Events (4)
| Tool | What It Does |
|---|---|
| `get_ingress_status()` | All ingresses + ALB addresses |
| `describe_ingress(name, namespace)` | Ingress details |
| `get_cluster_events(limit)` | Recent non-Normal events |
| `get_warning_events()` | Warning events only |

### Prometheus Tools (4)
| Tool | What It Does |
|---|---|
| `query_prometheus(promql)` | Run any PromQL query |
| `check_targets_down()` | Find down scrape targets |
| `check_container_restarts_prometheus()` | Restarts in last hour |
| `check_pod_memory_usage(namespace)` | Memory per pod |

### Health Summary (1)
| Tool | What It Does |
|---|---|
| `cluster_health_summary()` | Full cluster report |

### GitHub Tools (6)
| Tool | What It Does |
|---|---|
| `list_repos()` | All repos for owner |
| `list_pull_requests(repo, state)` | PRs for a repo |
| `get_recent_commits(repo, count)` | Recent commits |
| `create_issue(repo, title, body)` | Create an issue |
| `get_workflow_runs(repo, count)` | CI/CD run status |
| `get_repo_branches(repo)` | List branches |

### AWS Tools (7)
| Tool | What It Does |
|---|---|
| `list_ec2_instances()` | All EC2 with state |
| `check_ecr_images(repo)` | Recent ECR images |
| `list_ecr_repos()` | All ECR repos |
| `check_eks_cluster()` | EKS cluster status |
| `check_cloudwatch_alarms()` | Alarm states |
| `get_aws_account_info()` | Account ID + caller |
| `check_alb_health()` | ALB status + DNS |
| `check_route53_records(zone)` | DNS records |

### RAG Tools (3) — NEW
| Tool | What It Does |
|---|---|
| `search_runbook(query)` | General doc search |
| `search_troubleshooting(error)` | Find fixes for errors |
| `search_deployment_steps(component)` | Setup instructions |

---

## Usage Examples

### Example 1: Live Monitoring
```
You: "Are there any failing pods?"

Agent calls: check_failing_pods()
Agent responds: "2 pods failing — order-service ImagePullBackOff, sonarqube CrashLoopBackOff"
```

### Example 2: RAG — Find Past Fix
```
You: "How did we fix ImagePullBackOff before?"

Agent calls: search_troubleshooting("ImagePullBackOff")
Agent responds: "Based on our docs, this was caused by an image tag that didn't exist
in ECR. Fix: update values-order.yaml to use an existing tag like 'latest12'"
```

### Example 3: Combined MCP + RAG
```
You: "Something is wrong with Jenkins, help me fix it"

Agent calls: list_pods(namespace="jenkins")     → finds pod Init:0/2
Agent calls: describe_pod("jenkins-0", "jenkins") → sees missing secret error
Agent calls: search_troubleshooting("jenkins-admin-secret not found")
Agent responds: "Jenkins pod is stuck because the admin secret doesn't exist.
Based on our troubleshooting docs, the fix is:
  kubectl create secret generic jenkins-admin-secret
    --from-literal=jenkins-admin-user=admin
    --from-literal=jenkins-admin-password=YOUR_PASSWORD
    -n jenkins"
```

### Example 4: Deployment Steps
```
You: "How do I set up monitoring?"

Agent calls: search_deployment_steps("monitoring Prometheus Grafana")
Agent responds: "From our deployment guide:
  1. Create namespace and grafana-admin-secret first
  2. Run: bash scripts/05-install-monitoring.sh
  3. Apply ingress: kubectl apply -f kubernetes/ingress/grafana-ingress.yaml
  4. Add Route53 CNAME for grafana.vosukula.online"
```

---

## Re-Index Documents (When Docs Change)

```bash
cd mcp-server
python rag/ingest.py
```

Run this whenever you update:
- README files
- Deployment guides
- Troubleshooting notes
- Kubernetes manifests
- Jenkinsfile

---

## Troubleshooting

| Issue | Fix |
|---|---|
| `ModuleNotFoundError: chromadb` | `pip install -r requirements.txt` |
| `RAG database not found` | Run `python rag/ingest.py` first |
| `No relevant documentation found` | Re-run ingest, check document paths |
| `kubectl: command not found` | Set `KUBECTL_PATH` env var or install kubectl |
| `Unable to connect to server` (EKS) | Run `aws eks update-kubeconfig` |
| Prometheus queries fail | Start port-forward: `kubectl port-forward svc/monitoring-... 9090:9090` |
| GitHub tools fail | Set `GITHUB_TOKEN` environment variable |
| Slow first query | Normal — model loads on first use (~5 sec), subsequent queries are fast |

---

## File Structure

```
mcp-server/
├── mcp_server.py              ← Main server (38 tools: kubectl + prometheus + github + aws + rag)
├── requirements.txt           ← All Python dependencies
├── README.md                  ← MCP server overview
├── tools_aws.py               ← (optional) AWS tool helpers
├── tools_github.py            ← (optional) GitHub tool helpers
└── rag/
    ├── ingest.py              ← Document indexer (run once to build vector DB)
    ├── query.py               ← Search engine (called by MCP tools)
    ├── requirements.txt       ← RAG-specific dependencies
    ├── README.md              ← RAG module docs
    └── chroma_db/             ← Vector database (auto-created by ingest.py)
```

---

## Quick Start (TL;DR)

```bash
# 1. Install everything
cd mcp-server
pip install -r requirements.txt

# 2. Set GitHub token
export GITHUB_TOKEN="ghp_your_token"

# 3. Index your docs (RAG)
python rag/ingest.py

# 4. Start the MCP server
python mcp_server.py

# 5. Connect Kiro (already configured in .kiro/settings/mcp.json)
# Ask questions in Kiro chat!
```

---

## Interview Explanation (2-minute version)

> "I built an AI-powered DevOps monitoring agent that combines live cluster monitoring with historical knowledge search.
>
> The MCP server exposes 38 tools — kubectl operations, Prometheus metrics, GitHub API, and AWS CLI — all callable through natural language via the Model Context Protocol.
>
> I also added RAG (Retrieval-Augmented Generation) using ChromaDB and SentenceTransformers. It indexes all our project documentation — deployment guides, troubleshooting notes, Kubernetes manifests. When the agent detects a failing pod, it can also search our docs to find how we fixed similar issues before.
>
> For example: agent detects ImagePullBackOff → checks ECR images → searches docs → tells me 'this happened before because tag v99 doesn't exist, available tags are latest12, latest11. Update values-order.yaml.'
>
> Everything runs locally — no external API calls for embeddings. The vector database is ChromaDB (file-based), embeddings use all-MiniLM-L6-v2 (90MB model on CPU). Total setup time: 5 minutes."
