"""
GitHub MCP Tools
================
Provides tools to interact with GitHub repositories, PRs, issues, and workflows.

Requirements:
  pip install PyGithub

Environment:
  export GITHUB_TOKEN="ghp_your_personal_access_token"
  export GITHUB_OWNER="ShivaKrishna44"

Generate token: GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
Required scopes: repo, workflow
"""

import os
from fastmcp import FastMCP

mcp = FastMCP("GitHub Tools")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_OWNER = os.getenv("GITHUB_OWNER", "ShivaKrishna44")


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


if __name__ == "__main__":
    print(f"GitHub Tools MCP Server — Owner: {GITHUB_OWNER}")
    print(f"Token: {'configured' if GITHUB_TOKEN else 'NOT SET'}")
    mcp.run()
