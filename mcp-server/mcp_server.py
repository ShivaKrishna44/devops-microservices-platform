"""
MCP Server for DevOps Monitoring & Kubernetes Operations
=========================================================
Exposes kubectl, Prometheus, GitHub, and AWS as MCP tools
that an AI agent can call to detect failures, diagnose issues,
manage repositories, and monitor cloud resources.

Usage:
  pip install fastmcp requests boto3 PyGithub
  python mcp_server.py

Environment Variables (set before running):
  GITHUB_TOKEN    — GitHub Personal Access Token (for GitHub tools)
  AWS_REGION      — AWS region (default: us-east-1)
  PROMETHEUS_URL  — Prometheus URL (default: http://localhost:9090)

Tools provided (35+):
  Kubernetes: list_pods, check_failing_pods, cluster_health_summary, ...
  Prometheus: query_prometheus, check_targets_down, ...
  GitHub: list_repos, list_prs, create_issue, get_workflow_runs, ...
  AWS: list_ec2_instances, check_ecr_images, get_cloudwatch_alarm, ...
"""

import subprocess
import json
import os
from fastmcp import FastMCP

mcp = FastMCP("DevOps Platform Monitor")

# --- Configuration ---
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
KUBECTL = os.getenv("KUBECTL_PATH", "kubectl")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_OWNER = os.getenv("GITHUB_OWNER", "ShivaKrishna44")


def run_kubectl(args: list) -> str:
    """Helper to run kubectl commands and return output."""
    try:
        result = subprocess.run(
            [KUBECTL] + args,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout or result.stderr
    except subprocess.TimeoutExpired:
        return "Error: kubectl command timed out after 30 seconds"
    except Exception as e:
        return f"Error: {str(e)}"


# ==========================================
# Pod Operations
# ==========================================

@mcp.tool
def list_pods(namespace: str = "default") -> str:
    """List all pods in a namespace with their status, restarts, and age."""
    return run_kubectl(["get", "pods", "-n", namespace, "-o", "wide"])


@mcp.tool
def list_all_pods() -> str:
    """List ALL pods across all namespaces — shows the full cluster state."""
    return run_kubectl(["get", "pods", "-A", "-o", "wide"])


@mcp.tool
def describe_pod(pod_name: str, namespace: str = "default") -> str:
    """Get detailed info about a pod including events, conditions, and volumes."""
    return run_kubectl(["describe", "pod", pod_name, "-n", namespace])


@mcp.tool
def get_pod_logs(pod_name: str, namespace: str = "default", lines: int = 50) -> str:
    """Get the last N lines of logs from a pod."""
    return run_kubectl(["logs", pod_name, "-n", namespace, f"--tail={lines}"])


@mcp.tool
def get_pod_events(pod_name: str, namespace: str = "default") -> str:
    """Get recent events for a specific pod — shows scheduling, pulling, errors."""
    return run_kubectl([
        "get", "events", "-n", namespace,
        "--field-selector", f"involvedObject.name={pod_name}",
        "--sort-by=.lastTimestamp"
    ])


# ==========================================
# Failure Detection
# ==========================================

@mcp.tool
def check_failing_pods() -> str:
    """Detect ALL pods NOT in Running/Completed state across the cluster.
    This is the #1 health check — shows CrashLoopBackOff, ImagePullBackOff, Pending, etc."""
    result = run_kubectl(["get", "pods", "-A"])
    lines = result.strip().split("\n")
    header = lines[0] if lines else ""
    failing = [line for line in lines[1:] if "Running" not in line and "Completed" not in line]
    if not failing:
        return "✅ All pods are healthy (Running or Completed)"
    return f"⚠️ {len(failing)} failing pods found:\n{header}\n" + "\n".join(failing)


@mcp.tool
def check_high_restarts(threshold: int = 3) -> str:
    """Find pods that have restarted more than threshold times — indicates instability."""
    result = run_kubectl([
        "get", "pods", "-A",
        "-o", "jsonpath={range .items[*]}{.metadata.namespace}/{.metadata.name} restarts={.status.containerStatuses[0].restartCount}\\n{end}"
    ])
    lines = result.strip().split("\n")
    high_restart = [line for line in lines if line and f"restarts=" in line]
    problematic = []
    for line in high_restart:
        try:
            count = int(line.split("restarts=")[1])
            if count > threshold:
                problematic.append(line)
        except (ValueError, IndexError):
            continue
    if not problematic:
        return f"✅ No pods with more than {threshold} restarts"
    return f"⚠️ {len(problematic)} pods with high restarts:\n" + "\n".join(problematic)


@mcp.tool
def check_pending_pods() -> str:
    """Find pods stuck in Pending state — usually means resource pressure or scheduling issues."""
    result = run_kubectl(["get", "pods", "-A", "--field-selector=status.phase=Pending"])
    if "No resources found" in result:
        return "✅ No pending pods"
    return f"⚠️ Pending pods (can't be scheduled):\n{result}"


# ==========================================
# Node & Resource Monitoring
# ==========================================

@mcp.tool
def get_node_status() -> str:
    """Check node health — shows Ready/NotReady status and resource pressure."""
    return run_kubectl(["get", "nodes", "-o", "wide"])


@mcp.tool
def get_node_resource_usage() -> str:
    """Show CPU and memory usage per node (requires metrics-server)."""
    return run_kubectl(["top", "nodes"])


@mcp.tool
def check_high_cpu(threshold: int = 80) -> str:
    """Find pods using high CPU — sorted by CPU usage."""
    return run_kubectl(["top", "pods", "-A", "--sort-by=cpu"])


@mcp.tool
def check_high_memory() -> str:
    """Find pods using high memory — sorted by memory usage."""
    return run_kubectl(["top", "pods", "-A", "--sort-by=memory"])


# ==========================================
# Deployments & Workloads
# ==========================================

@mcp.tool
def get_deployments(namespace: str = "default") -> str:
    """List all deployments with their desired/current/available replica counts."""
    return run_kubectl(["get", "deployments", "-n", namespace, "-o", "wide"])


@mcp.tool
def get_all_deployments() -> str:
    """List ALL deployments across all namespaces."""
    return run_kubectl(["get", "deployments", "-A"])


@mcp.tool
def check_rollout_status(deployment: str, namespace: str = "default") -> str:
    """Check if a deployment rollout is complete or stuck."""
    return run_kubectl(["rollout", "status", f"deployment/{deployment}", "-n", namespace, "--timeout=5s"])


# ==========================================
# Ingress & Networking
# ==========================================

@mcp.tool
def get_ingress_status() -> str:
    """Check all ingresses across namespaces — shows ALB addresses and hosts."""
    return run_kubectl(["get", "ingress", "-A"])


@mcp.tool
def describe_ingress(name: str, namespace: str = "default") -> str:
    """Get detailed ingress info including ALB events and backend health."""
    return run_kubectl(["describe", "ingress", name, "-n", namespace])


# ==========================================
# Cluster Events
# ==========================================

@mcp.tool
def get_cluster_events(limit: int = 20) -> str:
    """Get recent cluster-wide events — shows warnings, errors, scheduling issues.
    This is often the FIRST place to look when something goes wrong."""
    result = run_kubectl([
        "get", "events", "-A",
        "--sort-by=.lastTimestamp",
        f"--field-selector=type!=Normal"
    ])
    lines = result.strip().split("\n")
    # Return only last N events
    if len(lines) > limit + 1:
        return "\n".join(lines[:1] + lines[-(limit):])
    return result


@mcp.tool
def get_warning_events() -> str:
    """Get only WARNING events — filtered to show only problems."""
    return run_kubectl([
        "get", "events", "-A",
        "--field-selector=type=Warning",
        "--sort-by=.lastTimestamp"
    ])


# ==========================================
# Prometheus Queries
# ==========================================

@mcp.tool
def query_prometheus(promql: str) -> str:
    """Run a PromQL query against Prometheus.
    
    Requires port-forward to be active:
      kubectl port-forward svc/monitoring-kube-prometheus-prometheus -n monitoring 9090:9090
    
    Example queries:
      - 'up' (check which targets are up)
      - 'container_memory_usage_bytes{namespace="order-service"}' (memory usage)
      - 'rate(container_cpu_usage_seconds_total[5m])' (CPU rate)
      - 'kube_pod_container_status_restarts_total > 3' (high restart pods)
    """
    try:
        import requests
        response = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": promql},
            timeout=10,
        )
        data = response.json()
        if data.get("status") == "success":
            results = data.get("data", {}).get("result", [])
            if not results:
                return "Query returned no results"
            # Format results readably
            output = []
            for r in results[:20]:  # Limit to 20 results
                metric = r.get("metric", {})
                value = r.get("value", [None, None])[1]
                output.append(f"{json.dumps(metric, indent=2)}: {value}")
            return "\n".join(output)
        return f"Query error: {data.get('error', 'unknown')}"
    except ImportError:
        return "Error: 'requests' library not installed. Run: pip install requests"
    except Exception as e:
        return f"Error querying Prometheus: {str(e)}. Is port-forward active?"


@mcp.tool
def check_targets_down() -> str:
    """Check if any Prometheus scrape targets are down."""
    return query_prometheus("up == 0")


@mcp.tool
def check_container_restarts_prometheus() -> str:
    """Find containers with restarts in last hour using Prometheus metrics."""
    return query_prometheus("increase(kube_pod_container_status_restarts_total[1h]) > 0")


@mcp.tool
def check_pod_memory_usage(namespace: str = "order-service") -> str:
    """Get memory usage for pods in a namespace via Prometheus."""
    return query_prometheus(
        f'sum(container_memory_usage_bytes{{namespace="{namespace}"}}) by (pod) / 1024 / 1024'
    )


# ==========================================
# Health Summary
# ==========================================

@mcp.tool
def cluster_health_summary() -> str:
    """Run a comprehensive health check on the entire cluster.
    Returns a summary of: nodes, failing pods, high restarts, pending pods, and warning events."""
    summary = []
    
    # Nodes
    summary.append("=== NODES ===")
    summary.append(run_kubectl(["get", "nodes"]))
    
    # Failing pods
    summary.append("\n=== FAILING PODS ===")
    summary.append(check_failing_pods())
    
    # High restarts
    summary.append("\n=== HIGH RESTARTS ===")
    summary.append(check_high_restarts())
    
    # Pending pods
    summary.append("\n=== PENDING PODS ===")
    summary.append(check_pending_pods())
    
    # Recent warnings
    summary.append("\n=== RECENT WARNINGS (last 10) ===")
    result = run_kubectl([
        "get", "events", "-A",
        "--field-selector=type=Warning",
        "--sort-by=.lastTimestamp"
    ])
    lines = result.strip().split("\n")
    summary.append("\n".join(lines[:11]))  # header + 10 events
    
    return "\n".join(summary)


# ==========================================
# GitHub Operations
# ==========================================

@mcp.tool
def list_repos() -> str:
    """List all repositories for the configured GitHub owner."""
    try:
        from github import Github
        g = Github(GITHUB_TOKEN)
        user = g.get_user(GITHUB_OWNER)
        repos = []
        for repo in user.get_repos():
            repos.append(f"  {repo.name} — {repo.description or 'no description'} ({'private' if repo.private else 'public'})")
        return f"Repositories for {GITHUB_OWNER}:\n" + "\n".join(repos[:20])
    except Exception as e:
        return f"Error: {str(e)}. Is GITHUB_TOKEN set?"


@mcp.tool
def list_pull_requests(repo_name: str, state: str = "open") -> str:
    """List pull requests for a repository. State: open, closed, all."""
    try:
        from github import Github
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(f"{GITHUB_OWNER}/{repo_name}")
        prs = repo.get_pulls(state=state)
        result = []
        for pr in prs[:10]:
            result.append(f"  #{pr.number} [{pr.state}] {pr.title} (by {pr.user.login})")
        if not result:
            return f"No {state} pull requests in {repo_name}"
        return f"Pull Requests ({state}) for {repo_name}:\n" + "\n".join(result)
    except Exception as e:
        return f"Error: {str(e)}"


@mcp.tool
def get_recent_commits(repo_name: str, count: int = 10) -> str:
    """Get the most recent commits for a repository."""
    try:
        from github import Github
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(f"{GITHUB_OWNER}/{repo_name}")
        commits = repo.get_commits()[:count]
        result = []
        for c in commits:
            msg = c.commit.message.split("\n")[0][:60]
            result.append(f"  {c.sha[:7]} — {msg} ({c.commit.author.name})")
        return f"Recent commits in {repo_name}:\n" + "\n".join(result)
    except Exception as e:
        return f"Error: {str(e)}"


@mcp.tool
def create_issue(repo_name: str, title: str, body: str = "") -> str:
    """Create a new GitHub issue in a repository."""
    try:
        from github import Github
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(f"{GITHUB_OWNER}/{repo_name}")
        issue = repo.create_issue(title=title, body=body)
        return f"✅ Issue created: #{issue.number} — {issue.title}\n   URL: {issue.html_url}"
    except Exception as e:
        return f"Error creating issue: {str(e)}"


@mcp.tool
def get_workflow_runs(repo_name: str, count: int = 5) -> str:
    """Get recent GitHub Actions workflow runs (CI/CD status)."""
    try:
        from github import Github
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(f"{GITHUB_OWNER}/{repo_name}")
        runs = repo.get_workflow_runs()[:count]
        result = []
        for run in runs:
            status_icon = "✅" if run.conclusion == "success" else "❌" if run.conclusion == "failure" else "⏳"
            result.append(f"  {status_icon} {run.name} — {run.conclusion or 'in_progress'} ({run.created_at.strftime('%Y-%m-%d %H:%M')})")
        if not result:
            return f"No workflow runs found in {repo_name}"
        return f"GitHub Actions runs for {repo_name}:\n" + "\n".join(result)
    except Exception as e:
        return f"Error: {str(e)}"


@mcp.tool
def get_repo_branches(repo_name: str) -> str:
    """List all branches in a repository."""
    try:
        from github import Github
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(f"{GITHUB_OWNER}/{repo_name}")
        branches = [f"  {b.name}" + (" ← default" if b.name == repo.default_branch else "") for b in repo.get_branches()]
        return f"Branches in {repo_name}:\n" + "\n".join(branches[:20])
    except Exception as e:
        return f"Error: {str(e)}"


# ==========================================
# AWS Operations
# ==========================================

def run_aws(args: list) -> str:
    """Helper to run AWS CLI commands."""
    try:
        result = subprocess.run(
            ["aws"] + args + ["--region", AWS_REGION, "--output", "json"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return f"AWS Error: {result.stderr}"
        return result.stdout
    except Exception as e:
        return f"Error: {str(e)}"


@mcp.tool
def list_ec2_instances() -> str:
    """List all EC2 instances with their state, type, and name."""
    raw = run_aws(["ec2", "describe-instances",
                   "--query", "Reservations[].Instances[].{ID:InstanceId,State:State.Name,Type:InstanceType,Name:Tags[?Key=='Name']|[0].Value,IP:PublicIpAddress}"])
    try:
        instances = json.loads(raw)
        result = []
        for i in instances:
            state_icon = "🟢" if i.get("State") == "running" else "🔴"
            result.append(f"  {state_icon} {i.get('Name','unnamed')} — {i.get('ID')} ({i.get('Type')}) IP: {i.get('IP','none')} [{i.get('State')}]")
        if not result:
            return "No EC2 instances found"
        return "EC2 Instances:\n" + "\n".join(result)
    except json.JSONDecodeError:
        return raw


@mcp.tool
def check_ecr_images(repo_name: str = "order-service") -> str:
    """List recent images in an ECR repository with tags and push dates."""
    raw = run_aws(["ecr", "describe-images", "--repository-name", repo_name,
                   "--query", "imageDetails | sort_by(@, &imagePushedAt) | [-5:].[imageTags[0],imagePushedAt,imageSizeInBytes]"])
    try:
        images = json.loads(raw)
        result = []
        for img in images:
            tag = img[0] or "untagged"
            pushed = img[1][:19] if img[1] else "unknown"
            size_mb = round(img[2] / 1024 / 1024, 1) if img[2] else 0
            result.append(f"  {tag} — pushed {pushed} ({size_mb} MB)")
        if not result:
            return f"No images found in {repo_name}"
        return f"ECR Images in {repo_name} (latest 5):\n" + "\n".join(result)
    except json.JSONDecodeError:
        return raw


@mcp.tool
def list_ecr_repos() -> str:
    """List all ECR repositories in the account."""
    raw = run_aws(["ecr", "describe-repositories",
                   "--query", "repositories[].{Name:repositoryName,URI:repositoryUri,Scan:imageScanningConfiguration.scanOnPush}"])
    try:
        repos = json.loads(raw)
        result = []
        for r in repos:
            scan = "✅ scan" if r.get("Scan") else "❌ no scan"
            result.append(f"  {r.get('Name')} — {scan}")
        return "ECR Repositories:\n" + "\n".join(result)
    except json.JSONDecodeError:
        return raw


@mcp.tool
def check_eks_cluster() -> str:
    """Get EKS cluster status, version, and endpoint."""
    raw = run_aws(["eks", "describe-cluster", "--name", "expense-dev",
                   "--query", "cluster.{Name:name,Status:status,Version:version,Endpoint:endpoint,PlatformVersion:platformVersion}"])
    try:
        cluster = json.loads(raw)
        return f"""EKS Cluster:
  Name: {cluster.get('Name')}
  Status: {cluster.get('Status')}
  Version: {cluster.get('Version')}
  Platform: {cluster.get('PlatformVersion')}
  Endpoint: {cluster.get('Endpoint')[:50]}..."""
    except json.JSONDecodeError:
        return raw


@mcp.tool
def check_cloudwatch_alarms() -> str:
    """List all CloudWatch alarms and their current state."""
    raw = run_aws(["cloudwatch", "describe-alarms",
                   "--query", "MetricAlarms[].{Name:AlarmName,State:StateValue,Metric:MetricName}"])
    try:
        alarms = json.loads(raw)
        if not alarms:
            return "No CloudWatch alarms configured"
        result = []
        for a in alarms:
            icon = "🔴" if a.get("State") == "ALARM" else "🟢"
            result.append(f"  {icon} {a.get('Name')} — {a.get('State')} (metric: {a.get('Metric')})")
        return "CloudWatch Alarms:\n" + "\n".join(result)
    except json.JSONDecodeError:
        return raw


@mcp.tool
def get_aws_account_info() -> str:
    """Get current AWS account ID and caller identity."""
    raw = run_aws(["sts", "get-caller-identity"])
    try:
        info = json.loads(raw)
        return f"""AWS Account:
  Account ID: {info.get('Account')}
  ARN: {info.get('Arn')}
  User ID: {info.get('UserId')}"""
    except json.JSONDecodeError:
        return raw


@mcp.tool
def check_alb_health(alb_name: str = "") -> str:
    """List all ALBs and their state. If alb_name provided, show details for that one."""
    raw = run_aws(["elbv2", "describe-load-balancers",
                   "--query", "LoadBalancers[].{Name:LoadBalancerName,State:State.Code,DNS:DNSName,Type:Type}"])
    try:
        albs = json.loads(raw)
        result = []
        for alb in albs:
            icon = "🟢" if alb.get("State") == "active" else "🔴"
            result.append(f"  {icon} {alb.get('Name')} — {alb.get('State')} ({alb.get('Type')})\n     DNS: {alb.get('DNS')}")
        if not result:
            return "No ALBs found"
        return "Application Load Balancers:\n" + "\n".join(result)
    except json.JSONDecodeError:
        return raw


@mcp.tool
def check_route53_records(zone_name: str = "vosukula.online") -> str:
    """List Route53 DNS records for the hosted zone."""
    # First get zone ID
    raw = run_aws(["route53", "list-hosted-zones-by-name", "--dns-name", zone_name,
                   "--query", "HostedZones[0].Id"])
    try:
        zone_id = json.loads(raw).replace("/hostedzone/", "")
        records_raw = run_aws(["route53", "list-resource-record-sets",
                               "--hosted-zone-id", zone_id,
                               "--query", "ResourceRecordSets[].{Name:Name,Type:Type,Value:ResourceRecords[0].Value || AliasTarget.DNSName}"])
        records = json.loads(records_raw)
        result = []
        for r in records[:20]:
            result.append(f"  {r.get('Name')} [{r.get('Type')}] → {r.get('Value','alias')}")
        return f"Route53 Records ({zone_name}):\n" + "\n".join(result)
    except (json.JSONDecodeError, AttributeError):
        return raw


# ==========================================
# Run Server
# ==========================================

if __name__ == "__main__":
    print("Starting DevOps Platform Monitor MCP Server...")
    print(f"  kubectl: {KUBECTL}")
    print(f"  Prometheus: {PROMETHEUS_URL}")
    print(f"  AWS Region: {AWS_REGION}")
    print(f"  GitHub Owner: {GITHUB_OWNER}")
    print(f"  GitHub Token: {'configured' if GITHUB_TOKEN else 'NOT SET (GitHub tools will fail)'}")
    print("\nTools: kubectl, prometheus, github, aws")
    mcp.run()
