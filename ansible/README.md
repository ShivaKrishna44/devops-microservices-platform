# Ansible — Configuration Management for DevOps Platform

Ansible playbooks for automating Jenkins agent setup and EKS cluster bootstrap.

---

## Directory Structure

```
ansible/
├── ansible.cfg                      ← Ansible configuration
├── inventory/
│   └── hosts.ini                    ← Target hosts (Jenkins agent EC2)
├── group_vars/
│   └── jenkins_agents.yml           ← Variables for agent group
├── playbooks/
│   ├── setup-jenkins-agent.yml      ← Configure Jenkins agent EC2
│   └── bootstrap-cluster.yml        ← Orchestrate full cluster setup
├── templates/
│   └── jenkins-agent.service.j2     ← systemd service template
└── README.md                        ← This file
```

---

## Prerequisites

```bash
# Install Ansible (on your local machine or bastion)
pip install ansible

# Or on Mac:
brew install ansible

# Verify
ansible --version
```

---

## Playbook 1: Setup Jenkins Agent

Configures an EC2 instance as a Jenkins build agent with all required tools.

**What it installs:**
- Java 21 (OpenJDK)
- Git
- Docker
- kubectl
- Helm
- Terraform
- SonarQube Scanner
- Jenkins agent.jar + systemd service

### Usage

```bash
cd ansible

# 1. Update inventory with agent IP
vim inventory/hosts.ini
# Replace <AGENT_PUBLIC_IP> with actual IP

# 2. Run the playbook
ansible-playbook playbooks/setup-jenkins-agent.yml

# 3. To set the Jenkins agent secret (from Jenkins UI)
ansible-playbook playbooks/setup-jenkins-agent.yml \
  -e "jenkins_agent_secret=YOUR_SECRET_FROM_JENKINS"
```

### Why Ansible Over Bash Script?

| Feature | Bash Script | Ansible |
|---|---|---|
| Idempotent | ❌ (fails on re-run) | ✅ (safe to run multiple times) |
| Error handling | Basic (set -e) | Per-task with retries |
| Multiple servers | ❌ (run manually on each) | ✅ (runs on all hosts in parallel) |
| Variables | Hardcoded or env vars | Centralized in group_vars |
| Templates | Not supported | Jinja2 templates |
| Dry-run | Not possible | `--check` mode |
| Logging | Manual echo | Built-in task reporting |

---

## Playbook 2: Bootstrap EKS Cluster

Orchestrates the full cluster setup after `terraform apply`.

**What it does (in order):**
1. Verifies cluster connectivity
2. Creates all namespaces
3. Creates K8s secrets (Jenkins, Grafana) — **BEFORE** Helm installs
4. Installs ALB Controller
5. Installs Jenkins (waits for pod Ready)
6. Installs ArgoCD
7. Installs Monitoring (Prometheus + Grafana)
8. Installs SonarQube
9. Installs Argo Rollouts
10. Applies all ingress resources
11. Applies ArgoCD Application CRDs
12. Final verification (pods + ingresses)

### Usage

```bash
cd ansible

# Run the full bootstrap
ansible-playbook playbooks/bootstrap-cluster.yml

# With custom passwords
ansible-playbook playbooks/bootstrap-cluster.yml \
  -e "jenkins_admin_password=MyPass123" \
  -e "grafana_admin_password=GrafPass456"
```

### Why This Matters

**Before (manual):**
```bash
bash scripts/01-install-tools.sh        # might forget
kubectl create secret ...                # might forget this!
bash scripts/02-install-alb-controller.sh
bash scripts/03-install-jenkins.sh      # fails because secret missing!
# ... wait 50 minutes debugging Init:0/2 ...
```

**After (Ansible):**
```bash
ansible-playbook playbooks/bootstrap-cluster.yml
# Creates secrets FIRST, then installs — no more Init:0/2 stuck pods!
# Waits for each component to be ready before proceeding
# Reports success/failure per step
```

---

## Common Commands

```bash
# Check connectivity to agents
ansible jenkins_agents -m ping

# Run playbook in check mode (dry-run)
ansible-playbook playbooks/setup-jenkins-agent.yml --check

# Run specific tasks only (by tag)
ansible-playbook playbooks/setup-jenkins-agent.yml --tags "docker,kubectl"

# Run on specific host
ansible-playbook playbooks/setup-jenkins-agent.yml --limit jenkins-agent

# Show what would change (diff mode)
ansible-playbook playbooks/setup-jenkins-agent.yml --check --diff
```

---

## Troubleshooting

| Issue | Fix |
|---|---|
| `Permission denied (publickey)` | Check SSH key path in `hosts.ini` |
| `Unable to connect` | Verify Security Group allows SSH (port 22) |
| `dnf lock` error | Another process is running dnf — wait or kill it |
| `docker: permission denied` | Re-login as ec2-user (group change needs new session) |
| Playbook hangs at EKS step | Check AWS credentials on the agent |
