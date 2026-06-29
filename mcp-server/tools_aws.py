"""
AWS MCP Tools
=============
Provides tools to interact with AWS services: EC2, ECR, EKS, CloudWatch, ALB, Route53.

Requirements:
  pip install fastmcp

Prerequisites:
  - AWS CLI installed and configured (aws configure)
  - OR IAM instance profile (if running on EC2)

Environment:
  export AWS_REGION="us-east-1"  (optional, defaults to us-east-1)
"""

import subprocess
import json
import os
from fastmcp import FastMCP

mcp = FastMCP("AWS Tools")

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")


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
    except subprocess.TimeoutExpired:
        return "Error: AWS command timed out"
    except Exception as e:
        return f"Error: {str(e)}"


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
def list_ec2_instances() -> str:
    """List all EC2 instances with their state, type, name, and IP."""
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
def check_eks_cluster(cluster_name: str = "expense-dev") -> str:
    """Get EKS cluster status, version, and endpoint."""
    raw = run_aws(["eks", "describe-cluster", "--name", cluster_name,
                   "--query", "cluster.{Name:name,Status:status,Version:version,Endpoint:endpoint,PlatformVersion:platformVersion}"])
    try:
        cluster = json.loads(raw)
        return f"""EKS Cluster:
  Name: {cluster.get('Name')}
  Status: {cluster.get('Status')}
  Version: {cluster.get('Version')}
  Platform: {cluster.get('PlatformVersion')}
  Endpoint: {cluster.get('Endpoint')[:60]}..."""
    except json.JSONDecodeError:
        return raw


@mcp.tool
def check_cloudwatch_alarms() -> str:
    """List all CloudWatch alarms and their current state (OK, ALARM, INSUFFICIENT_DATA)."""
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
def check_alb_health() -> str:
    """List all Application Load Balancers with their state and DNS name."""
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
    """List Route53 DNS records for a hosted zone."""
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


if __name__ == "__main__":
    print(f"AWS Tools MCP Server — Region: {AWS_REGION}")
    mcp.run()
