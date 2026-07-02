# MCP Server — DevOps Kubernetes Monitor

AI-powered cluster monitoring using MCP (Model Context Protocol). Exposes kubectl and Prometheus as tools that an AI agent can call to detect failures and diagnose issues.

## Setup

```bash
cd mcp-server
pip install -r requirements.txt
```

## Run

```bash
python mcp_server.py
```

## Prerequisites

- `kubectl` configured and pointing to your EKS cluster
- For Prometheus queries, port-forward first:
  ```bash
  kubectl port-forward svc/monitoring-kube-prometheus-prometheus -n monitoring 9090:9090
  ```

## Available Tools (26 total)

### Pod Operations
| Tool | What It Does |
|---|---|
| `list_pods` | List pods in a namespace |
| `list_all_pods` | List ALL pods across cluster |
| `describe_pod` | Detailed pod info + events |
| `get_pod_logs` | Get pod logs (last N lines) |
| `get_pod_events` | Events for a specific pod |

### Failure Detection
| Tool | What It Does |
|---|---|
| `check_failing_pods` | Find pods NOT Running/Completed |
| `check_high_restarts` | Find pods restarting too often |
| `check_pending_pods` | Find pods stuck in Pending |

### Node & Resources
| Tool | What It Does |
|---|---|
| `get_node_status` | Node health (Ready/NotReady) |
| `get_node_resource_usage` | CPU/memory per node |
| `check_high_cpu` | Pods sorted by CPU |
| `check_high_memory` | Pods sorted by memory |

### Deployments
| Tool | What It Does |
|---|---|
| `get_deployments` | Deployment replica status |
| `get_all_deployments` | All deployments cluster-wide |
| `check_rollout_status` | Is a rollout stuck? |

### Ingress & Networking
| Tool | What It Does |
|---|---|
| `get_ingress_status` | All ingresses + ALB addresses |
| `describe_ingress` | Detailed ingress events |

### Events
| Tool | What It Does |
|---|---|
| `get_cluster_events` | Recent non-Normal events |
| `get_warning_events` | Warning events only |

### Prometheus Queries
| Tool | What It Does |
|---|---|
| `query_prometheus` | Run any PromQL query |
| `check_targets_down` | Find scrape targets that are down |
| `check_container_restarts_prometheus` | Restarts in last hour |
| `check_pod_memory_usage` | Memory usage per pod |

### Health Summary
| Tool | What It Does |
|---|---|
| `cluster_health_summary` | Full cluster health report (nodes + pods + events) |

## Example: Agent Conversation

```
User: "Is anything broken in the cluster?"

Agent calls: cluster_health_summary()
Agent responds: "2 pods are in ImagePullBackOff in the order-service namespace.
                The image tag 'v2.0' doesn't exist in ECR. Here's how to fix it..."
```

## Kiro MCP Configuration

Add to `.kiro/settings/mcp.json`:
```json
{
  "mcpServers": {
    "k8s-monitor": {
      "command": "python",
      "args": ["mcp-server/mcp_server.py"],
      "disabled": false
    }
  }
}
```


---

## User Manual — Step-by-Step Guide

This section explains how to set up, start, and use the MCP server from scratch.

---

### Step 1: Prerequisites

Before starting, make sure you have:

| Requirement | How to Check | Install If Missing |
|---|---|---|
| Python 3.9+ | `python --version` | [python.org](https://www.python.org/downloads/) |
| kubectl | `kubectl version --client` | [kubernetes.io](https://kubernetes.io/docs/tasks/tools/) |
| kubectl connected to EKS | `kubectl get nodes` | `aws eks update-kubeconfig --region us-east-1 --name expense-dev` |
| pip | `pip --version` | Comes with Python |

---

### Step 2: Install Dependencies

```bash
cd mcp-server
pip install -r requirements.txt
```

This installs:
- `fastmcp` — the MCP server framework
- `requests` — for Prometheus API calls

---

### Step 3: Verify kubectl Works

```bash
# Make sure kubectl can reach the cluster
kubectl get nodes
# Should show your EKS nodes

kubectl get pods -A
# Should list all pods
```

If this fails → fix kubeconfig first:
```bash
aws eks update-kubeconfig --region us-east-1 --name expense-dev
```

---

### Step 4: Start the MCP Server

```bash
cd mcp-server
python mcp_server.py
```

You'll see:
```
Starting DevOps Kubernetes Monitor MCP Server...
Tools available: list_pods, check_failing_pods, query_prometheus, cluster_health_summary, ...
```

The server is now running and waiting for tool calls from an AI agent.

---

### Step 5: Connect to Kiro (or any MCP-compatible agent)

#### Option A — Kiro IDE

Add to `.kiro/settings/mcp.json` in your workspace:
```json
{
  "mcpServers": {
    "k8s-monitor": {
      "command": "python",
      "args": ["mcp-server/mcp_server.py"],
      "disabled": false
    }
  }
}
```

Then in Kiro chat, you can ask:
- "Are there any failing pods in my cluster?"
- "What's the cluster health summary?"
- "Show me pods with high CPU usage"

Kiro will call the MCP tools automatically and show you results.

#### Option B — Claude Desktop

Add to `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "k8s-monitor": {
      "command": "python",
      "args": ["/full/path/to/mcp-server/mcp_server.py"]
    }
  }
}
```

Restart Claude Desktop → tools appear in the tool list.

#### Option C — Custom Python Agent

```python
from fastmcp import Client

async def main():
    client = Client("mcp_server.py")
    async with client:
        # Call any tool
        result = await client.call_tool("cluster_health_summary", {})
        print(result)
        
        # Check specific namespace
        result = await client.call_tool("list_pods", {"namespace": "order-service"})
        print(result)

import asyncio
asyncio.run(main())
```

---

### Step 6: Enable Prometheus Queries (Optional)

For Prometheus-based metrics (memory usage, CPU rate, etc.), you need port-forwarding:

```bash
# In a separate terminal:
kubectl port-forward svc/monitoring-kube-prometheus-prometheus -n monitoring 9090:9090
```

Keep this running while using the MCP server. Now tools like `query_prometheus`, `check_targets_down`, `check_pod_memory_usage` will work.

---

### Step 7: See Results

#### Example 1 — Ask "Is anything broken?"

Agent calls: `check_failing_pods()`

Result:
```
⚠️ 2 failing pods found:
NAMESPACE       NAME                              READY   STATUS             RESTARTS
order-service   order-service-abc123-xyz          0/1     ImagePullBackOff   0
sonarqube       sonarqube-sonarqube-0             0/1     CrashLoopBackOff   5
```

Agent explains: "order-service can't pull image — tag doesn't exist in ECR. SonarQube is crashing — check logs."

---

#### Example 2 — Ask "Check cluster health"

Agent calls: `cluster_health_summary()`

Result:
```
=== NODES ===
NAME                         STATUS   ROLES    AGE
ip-10-0-11-145.ec2.internal  Ready    <none>   5h
ip-10-0-12-87.ec2.internal   Ready    <none>   5h

=== FAILING PODS ===
✅ All pods are healthy (Running or Completed)

=== HIGH RESTARTS ===
✅ No pods with more than 3 restarts

=== PENDING PODS ===
✅ No pending pods

=== RECENT WARNINGS (last 10) ===
(none)
```

Agent responds: "Cluster is fully healthy. 2 nodes running, no failing pods, no warnings."

---

#### Example 3 — Ask "Show memory usage for order-service"

Agent calls: `check_pod_memory_usage(namespace="order-service")`

Result:
```
{"pod": "order-service-7d5d5cf5c7-2928"}: 45.2 (MB)
```

Agent responds: "order-service is using 45MB memory — well within the 256MB limit."

---

#### Example 4 — Ask "Why is this pod failing?"

Agent calls: `describe_pod(pod_name="order-service-abc123", namespace="order-service")`

Result shows Events section:
```
Warning  Failed   2m  kubelet  Error: ImagePullBackOff
Warning  Failed   2m  kubelet  Failed to pull image "589389425618.dkr.ecr.us-east-1.amazonaws.com/order-service:v99"
                                rpc error: code = NotFound
```

Agent responds: "Image tag `v99` doesn't exist in ECR. Available tags are `latest11`, `latest12`. Update the Helm values file or run the Jenkins pipeline with the correct tag."

---

### Troubleshooting the MCP Server

| Issue | Fix |
|---|---|
| `kubectl: command not found` | Install kubectl or set full path in `mcp_server.py` (`KUBECTL = "/usr/local/bin/kubectl"`) |
| `Unable to connect to the server` | Run `aws eks update-kubeconfig` first |
| Prometheus queries return errors | Start port-forward: `kubectl port-forward svc/monitoring-kube-prometheus-prometheus -n monitoring 9090:9090` |
| `fastmcp not found` | Run `pip install -r requirements.txt` |
| Server starts but tools don't work | Check kubectl access: `kubectl get pods -A` must work from the same terminal |
| Windows path issues | Change `KUBECTL = "kubectl"` to `KUBECTL = "./kubectl.exe"` in mcp_server.py |

---

### Architecture Diagram

```
┌─────────────┐         ┌──────────────────┐         ┌──────────────┐
│  AI Agent   │ ──MCP─→ │  mcp_server.py   │ ──CLI─→ │  Kubernetes  │
│ (Kiro/Claude)│        │  (FastMCP)       │         │  (EKS)       │
│             │ ←─JSON──│                  │ ←─JSON─ │              │
└─────────────┘         │  Tools:          │         └──────────────┘
                        │  - kubectl       │
                        │  - prometheus    │         ┌──────────────┐
                        │  - health checks │ ──HTTP→ │  Prometheus  │
                        └──────────────────┘         │  (metrics)   │
                                                     └──────────────┘
```

**Flow:**
1. You ask the AI agent a question ("Is anything broken?")
2. Agent decides which MCP tool to call (`check_failing_pods`)
3. MCP server runs `kubectl get pods -A` under the hood
4. Returns the output to the agent
5. Agent interprets the result and explains in plain English

---

### Quick Start (TL;DR)

```bash
# 1. Install
cd mcp-server && pip install -r requirements.txt

# 2. Verify kubectl works
kubectl get nodes

# 3. Start server
python mcp_server.py

# 4. Connect your AI agent (Kiro, Claude Desktop, or custom)

# 5. Ask questions like:
#    "Is anything broken in the cluster?"
#    "Show me pod health for order-service"
#    "What are the recent warning events?"
```
