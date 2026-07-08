# DevOps Interview Topics — Detailed Explanations with Examples

---

## 1. Git — Rebase, Squash, Stash, Branching, Release & Hotfix

---

### Rebase vs Merge

**Merge:** Creates a merge commit that combines two branches. History shows the branch existed.
```bash
git checkout main
git merge feature-branch
# Creates: merge commit with two parents
# History: shows the branch fork and merge point
```

**Rebase:** Replays your commits on TOP of the target branch. Linear history — looks like you worked directly on main.
```bash
git checkout feature-branch
git rebase main
# Moves your commits to the tip of main
# History: straight line, no fork visible
```

**When to use which:**
- Rebase: feature branches before merging to main (cleaner history)
- Merge: main/develop branches, shared branches (never rebase shared branches!)

**Real example:**
```
Before rebase:
main:    A → B → C
feature: A → B → D → E

After rebase (feature onto main):
main:    A → B → C
feature: A → B → C → D' → E'  (D and E replayed after C)
```

---

### Squash

**What:** Combine multiple commits into one before merging.

```bash
# You have 5 messy commits on feature branch:
# "wip", "fix typo", "another fix", "actually done", "really done"

# Squash into one clean commit:
git rebase -i HEAD~5
# In editor: change "pick" to "squash" for commits 2-5
# Result: one commit "Add user authentication feature"
```

**When to use:** Before merging feature branch to main — gives clean, meaningful commit history.

---

### Stash

**What:** Temporarily save uncommitted changes without committing them.

```bash
# You're working on feature, but need to switch to hotfix urgently:
git stash                    # Saves changes, working directory is clean
git checkout hotfix-branch   # Switch safely
# ... fix the hotfix ...
git checkout feature-branch
git stash pop                # Restore your saved changes
```

**Useful commands:**
```bash
git stash list               # See all stashes
git stash show -p stash@{0}  # See what's in a stash
git stash drop stash@{0}     # Delete a stash
git stash clear              # Delete all stashes
```

---

### Branching Strategy (GitFlow)

```
main ─────────────────────────────── (production releases)
  │
  ├── develop ────────────────────── (integration branch)
  │     │
  │     ├── feature/login ────────── (developer works here)
  │     ├── feature/payment ──────── (another developer)
  │     │
  │     └── release/1.0 ─────────── (pre-release testing)
  │
  └── hotfix/critical-bug ────────── (emergency fix from main)
```

**Rules:**
- `main` = production-ready code only
- `develop` = integration branch (features merge here)
- `feature/*` = individual features (branch from develop)
- `release/*` = prepare for release (from develop → main)
- `hotfix/*` = emergency fixes (branch from main → merge to both main AND develop)

---

### Release and Hotfix Flow

**Release flow:**
```bash
git checkout develop
git checkout -b release/2.0
# Test, fix minor bugs on release branch
git checkout main && git merge release/2.0
git tag v2.0
git checkout develop && git merge release/2.0
git branch -d release/2.0
```

**Hotfix flow (production is broken!):**
```bash
git checkout main
git checkout -b hotfix/fix-payment-crash
# Fix the bug
git commit -m "Fix: payment crash on null user"
git checkout main && git merge hotfix/fix-payment-crash
git tag v2.0.1
git checkout develop && git merge hotfix/fix-payment-crash  # backport fix
git branch -d hotfix/fix-payment-crash
```

---

## 2. Jenkins — Architecture, Upgrade, Pipeline Troubleshooting, Shared Libraries

---

### Jenkins Architecture

```
┌─────────────────────────────────────────────┐
│            Jenkins Controller                │
│  (manages UI, scheduling, config, plugins)  │
│  Runs on: EKS Pod (jenkins-0) or EC2        │
└──────────────┬──────────────────────────────┘
               │ JNLP / WebSocket
    ┌──────────┼──────────────────┐
    ▼          ▼                  ▼
┌────────┐ ┌────────┐      ┌────────────┐
│ Agent1 │ │ Agent2 │ ...  │ K8s Pod    │
│ (EC2)  │ │ (EC2)  │      │ (ephemeral)│
└────────┘ └────────┘      └────────────┘
```

**Components:**
- **Controller:** Manages jobs, UI, plugins. Does NOT run builds (in production).
- **Agents:** Execute builds. Can be: permanent EC2, ephemeral K8s pods, Docker containers.
- **Executors:** Number of parallel builds an agent can run (configurable per agent).
- **Workspace:** Directory on agent where code is checked out and built.

---

### Jenkins Upgrade Process

```bash
# 1. Backup first!
kubectl exec jenkins-0 -n jenkins -- tar czf /tmp/jenkins-backup.tar.gz /var/jenkins_home
kubectl cp jenkins/jenkins-0:/tmp/jenkins-backup.tar.gz ./jenkins-backup.tar.gz

# 2. Check compatibility
# Visit: https://www.jenkins.io/changelog/ — check plugin compatibility

# 3. For Helm-based Jenkins:
helm repo update
helm upgrade jenkins jenkins/jenkins -n jenkins -f kubernetes/jenkins/jenkins-values.yaml

# 4. For EC2 Jenkins:
sudo systemctl stop jenkins
sudo dnf update jenkins -y
sudo systemctl start jenkins

# 5. Verify:
# Jenkins UI → Manage Jenkins → check version + plugin status
```

**Rollback:**
```bash
# Helm:
helm rollback jenkins 1 -n jenkins  # Roll back to previous revision

# EC2:
sudo dnf downgrade jenkins-<previous-version>
sudo systemctl restart jenkins
```

---

### Pipeline Troubleshooting

**Common failures and debug commands:**

| Problem | Debug Command | Likely Fix |
|---|---|---|
| Agent offline | Check Jenkins → Nodes → agent status | Reconnect agent, check disk space |
| `script returned exit code 1` | Read console output — find the failing `sh` step | Fix the shell command |
| `No such DSL method` | Missing plugin for that pipeline step | Install the plugin |
| `java.lang.OutOfMemoryError` | Jenkins Controller OOM | Increase memory limits in Helm values |
| Build hangs indefinitely | Check for interactive prompt (apt -y missing) | Add `-y` flags, set timeout |
| Permission denied | `aws sts get-caller-identity` on agent | Fix IAM role/credentials |
| Docker: permission denied | `groups` command on agent | Add user to docker group |

**Debug a stuck build:**
```bash
# Check what the agent is doing:
kubectl exec -it jenkins-0 -n jenkins -- cat /var/jenkins_home/jobs/<job>/builds/<number>/log

# Check agent connectivity:
kubectl logs jenkins-0 -n jenkins -c jenkins | grep "agent"
```

---

### Shared Libraries

**What:** Reusable Groovy code shared across multiple Jenkinsfiles.

**Structure:**
```
jenkins-shared-library/
├── vars/
│   ├── dockerBuild.groovy     ← called as dockerBuild() in pipeline
│   ├── deployToEKS.groovy     ← called as deployToEKS() in pipeline
│   └── sonarScan.groovy       ← called as sonarScan() in pipeline
└── src/
    └── com/company/Utils.groovy  ← helper classes
```

**Example `vars/dockerBuild.groovy`:**
```groovy
def call(String serviceName, String tag) {
    sh """
        docker build -t ${serviceName}:${tag} .
        docker tag ${serviceName}:${tag} ${env.ECR_REGISTRY}/${serviceName}:${tag}
        docker push ${env.ECR_REGISTRY}/${serviceName}:${tag}
    """
}
```

**Usage in Jenkinsfile:**
```groovy
@Library('my-shared-library') _

pipeline {
    stages {
        stage('Build') {
            steps {
                dockerBuild('order-service', env.BUILD_NUMBER)
            }
        }
    }
}
```

**Configure in Jenkins:** Manage Jenkins → System → Global Pipeline Libraries → Add library (Git URL of the shared lib repo).

---

## 3. Docker — Dockerfile, CMD vs ENTRYPOINT, Networking, Volumes, Troubleshooting

---

### Dockerfile Components

```dockerfile
FROM python:3.11-slim          # Base image (start from here)
WORKDIR /app                   # Set working directory inside container
COPY requirements.txt .        # Copy file from host to container
RUN pip install -r requirements.txt  # Execute command during BUILD
COPY . .                       # Copy rest of code
RUN adduser --disabled-password appuser  # Create non-root user
USER appuser                   # Switch to non-root
EXPOSE 5000                    # Document which port app uses (doesn't publish)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]  # Default run command
```

**Build order matters (layer caching):**
- Put things that change RARELY first (base image, dependencies)
- Put things that change OFTEN last (app code)
- If a layer changes, all layers AFTER it are rebuilt

---

### CMD vs ENTRYPOINT

**CMD:** Default command. Can be overridden at runtime.
```dockerfile
CMD ["python", "app.py"]
# Run: docker run myapp          → runs "python app.py"
# Run: docker run myapp bash     → runs "bash" (CMD overridden!)
```

**ENTRYPOINT:** Fixed command. Arguments are appended.
```dockerfile
ENTRYPOINT ["python"]
CMD ["app.py"]
# Run: docker run myapp          → runs "python app.py"
# Run: docker run myapp test.py  → runs "python test.py" (CMD overridden, ENTRYPOINT stays)
```

**Best practice:** Use ENTRYPOINT for the executable, CMD for default arguments:
```dockerfile
ENTRYPOINT ["gunicorn"]
CMD ["--bind", "0.0.0.0:5000", "--workers", "2", "app:app"]
```

---

### Docker Networking

**Network types:**
| Type | Use Case | Example |
|---|---|---|
| bridge (default) | Containers on same host talk to each other | `docker network create mynet` |
| host | Container uses host's network directly | `docker run --network host` |
| none | No networking | Isolated containers |
| overlay | Multi-host (Swarm/K8s) | Cross-node communication |

**Example:**
```bash
# Create network
docker network create app-network

# Run containers on same network (they can reach each other by name)
docker run -d --name db --network app-network postgres
docker run -d --name app --network app-network -e DB_HOST=db myapp
# "app" container can reach "db" by hostname "db"
```

**Debug networking:**
```bash
docker network ls                          # List networks
docker network inspect bridge              # See connected containers
docker exec myapp ping db                  # Test connectivity
docker exec myapp curl http://db:5432      # Test port access
```

---

### Volumes

**Why:** Container filesystem is ephemeral — data is lost when container dies. Volumes persist data.

```bash
# Named volume (Docker manages the location)
docker volume create db-data
docker run -v db-data:/var/lib/postgresql/data postgres

# Bind mount (you choose the host path)
docker run -v /home/user/app:/app myapp

# In Dockerfile (declares a volume mount point)
VOLUME ["/var/lib/postgresql/data"]
```

**Debug volumes:**
```bash
docker volume ls                    # List all volumes
docker volume inspect db-data       # See mount path
docker exec myapp ls /app           # Check what's mounted
```

---

### Container Troubleshooting

| Problem | Debug Command | Fix |
|---|---|---|
| Container exits immediately | `docker logs <container>` | Fix app error (missing env var, crash) |
| Container won't start | `docker inspect <container> \| grep Error` | Check image exists, port conflicts |
| App not reachable | `docker port <container>` | Publish port: `-p 8080:5000` |
| Out of disk space | `docker system df` | `docker system prune -af` |
| Slow build | `docker build --no-cache .` | Fix layer caching order |
| Permission denied in container | `docker exec -u root <container> ls -la` | `chmod` or run as root to debug |

**Full debug flow:**
```bash
# 1. Is it running?
docker ps -a | grep myapp

# 2. Why did it die?
docker logs myapp --tail 50

# 3. Get inside to investigate:
docker exec -it myapp /bin/sh

# 4. Check resources:
docker stats myapp
```

---

## 4. Kubernetes — Services, CrashLoopBackOff, Deployments

---

### Kubernetes Services

**Service types:**
| Type | What It Does | Use Case |
|---|---|---|
| ClusterIP | Internal only (cluster-to-cluster) | Backend services talking to each other |
| NodePort | Exposes on each node's IP at a fixed port (30000-32767) | Quick dev/test access |
| LoadBalancer | Provisions external LB (AWS ALB/NLB) | Production internet-facing |
| ExternalName | DNS alias to external service | Pointing to external DB |

**Example ClusterIP:**
```yaml
apiVersion: v1
kind: Service
metadata:
  name: order-service
spec:
  type: ClusterIP
  selector:
    app: order-service    # Finds pods with this label
  ports:
    - port: 5000          # Service port (other pods use this)
      targetPort: 5000    # Container port (where app listens)
```

**How service discovery works:**
```bash
# From any pod in the cluster:
curl http://order-service.order-service.svc.cluster.local:5000
# Or short form (same namespace):
curl http://order-service:5000
```

---

### CrashLoopBackOff Troubleshooting

**What it means:** Container starts → crashes → K8s restarts it → crashes again → K8s waits longer → restart. Loop continues with exponential backoff (10s, 20s, 40s, ...).

**Debug step-by-step:**
```bash
# 1. See the status
kubectl get pods -n order-service
# NAME                     READY   STATUS             RESTARTS
# order-service-abc123     0/1     CrashLoopBackOff   5

# 2. WHY is it crashing? Check logs:
kubectl logs order-service-abc123 -n order-service
kubectl logs order-service-abc123 -n order-service --previous  # logs from LAST crash

# 3. Check events:
kubectl describe pod order-service-abc123 -n order-service
# Look at Events section at the bottom

# 4. Common causes:
```

| Cause | Log Shows | Fix |
|---|---|---|
| Missing env variable | `KeyError: 'DB_HOST'` | Add env var to deployment |
| Wrong command | `exec: "gunicorn": not found` | Fix CMD in Dockerfile |
| Port conflict | `Address already in use` | Change port or kill existing process |
| OOM Killed | Exit code 137 | Increase memory limits |
| Missing config/secret | `FileNotFoundError: config.yaml` | Mount ConfigMap/Secret |
| Dependency not ready | `Connection refused to db:5432` | Add init container or readiness check |

---

### Deployment Basics

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 2                    # Run 2 copies
  selector:
    matchLabels:
      app: order-service
  strategy:
    type: RollingUpdate          # Zero-downtime updates
    rollingUpdate:
      maxUnavailable: 1          # At most 1 pod down during update
      maxSurge: 1                # At most 1 extra pod during update
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: order-service
          image: 589389425618.dkr.ecr.us-east-1.amazonaws.com/order-service:latest11
          ports:
            - containerPort: 5000
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: 500m
              memory: 256Mi
```

**Useful deployment commands:**
```bash
kubectl rollout status deployment/order-service -n order-service    # Watch rollout
kubectl rollout history deployment/order-service -n order-service   # See revisions
kubectl rollout undo deployment/order-service -n order-service      # Rollback!
kubectl scale deployment/order-service --replicas=5 -n order-service  # Scale up
```

---

## 5. Terraform — End-to-End Workflow & Infrastructure Provisioning

---

### End-to-End Workflow

```
1. Write Code (.tf files)
     ↓
2. terraform init          ← Downloads providers + modules
     ↓
3. terraform plan          ← Shows what WILL change (dry run)
     ↓
4. Review plan output      ← Human checks before applying
     ↓
5. terraform apply         ← Creates/modifies real resources
     ↓
6. State updated           ← terraform.tfstate records what exists
     ↓
7. terraform destroy       ← Removes everything (when done)
```

### Infrastructure Provisioning Flow (our project)

```bash
# 1. Initialize (downloads AWS provider + EKS module)
cd Terraform
terraform init -backend-config=tfvars/dev/backend.tfvars

# 2. Plan (see what will be created)
terraform plan -var-file=tfvars/dev/dev.tfvars
# Output: "Plan: 47 to add, 0 to change, 0 to destroy"

# 3. Apply (create everything)
terraform apply -var-file=tfvars/dev/dev.tfvars
# Creates: VPC → Subnets → IGW → NAT → EKS → Node Groups → ECR → IAM

# 4. Verify
aws eks describe-cluster --name expense-dev --query cluster.status
# "ACTIVE"

# 5. Destroy (when done, saves cost)
terraform destroy -var-file=tfvars/dev/dev.tfvars
```

### What Each File Does

```
provider.tf    → Which cloud + version (AWS, ~> 6.0)
backend.tf     → Where to store state (S3 + DynamoDB)
variables.tf   → Input variables (cluster name, region, instance type)
vpc.tf         → VPC + subnets + NAT gateway
eks.tf         → EKS cluster + node groups
ecr.tf         → Container registries
iam-irsa.tf    → IAM roles for service accounts
output.tf      → Values to display after apply (cluster endpoint, VPC ID)
```

---

## 6. General Cloud Concepts — IaaS vs PaaS vs SaaS

---

| | IaaS | PaaS | SaaS |
|---|---|---|---|
| **What you manage** | OS, runtime, app, data | App + data only | Nothing (just use it) |
| **Provider manages** | Hardware, networking, virtualization | Everything below app | Everything |
| **Example** | EC2, VPC, EBS | Elastic Beanstalk, Lambda, EKS | Gmail, Salesforce, Slack |
| **Analogy** | Renting an empty apartment (you furnish it) | Renting a furnished apartment | Staying at a hotel |
| **Our project uses** | EC2 (Jenkins agent) | EKS (managed K8s control plane) | GitHub, SonarCloud |

**Real example from our project:**
- IaaS: EC2 instance for Jenkins agent (we manage OS, Docker, Java)
- PaaS: EKS cluster (AWS manages K8s control plane, we deploy pods)
- SaaS: GitHub (we just push code, they manage everything)

---

## 7. Straive-Style Questions — Architecture & Scenario-Based

---

### Cloud Migration Strategy (On-prem to AWS)

**Approach:**
```
Phase 1: Assessment (2-4 weeks)
  - Inventory all on-prem workloads
  - Classify each: Rehost, Replatform, Refactor, Retire, Retain
  - Identify dependencies between systems

Phase 2: Foundation (2-4 weeks)
  - Set up AWS Landing Zone (VPC, IAM, networking)
  - Establish Direct Connect / VPN to on-prem
  - Set up monitoring and security baseline

Phase 3: Migration (iterative)
  - Start with lowest-risk workloads
  - Use AWS DMS for database migration (continuous replication)
  - Use AWS CloudEndure for VM migration
  - Validate in parallel (both systems running)

Phase 4: Cutover
  - DNS switch (Route53 weighted → 10% → 50% → 100%)
  - Keep on-prem alive for 48h rollback window
  - Decommission after validation
```

**Rollback planning:**
- Keep on-prem running in read-only mode during cutover
- DMS can replicate in reverse (AWS → on-prem) if needed
- DNS rollback: switch Route53 back to on-prem IPs (TTL: 60s for fast switch)
- Test rollback BEFORE the actual migration

---

### Incident Management

**Performance degradation scenario:**
```
1. Detection: Grafana alert → p99 latency > 5s for 5 minutes
2. Triage: On-call checks dashboards → identifies affected service
3. Mitigation: Scale up replicas / rollback last deployment
4. Communication: Update status page, notify stakeholders
5. Resolution: Root cause found (DB connection pool exhausted)
6. Post-mortem: Write RCA, action items, prevent recurrence
```

**SLA handling:**
- SLA: 99.9% uptime = 43 min/month allowed downtime
- If SLA breached: communicate proactively to customer, offer credits
- Track with error budgets: when budget exhausted → freeze deployments

**RCA (Root Cause Analysis) process:**
```
1. Timeline: Build exact timeline of events (when detected, when mitigated, when resolved)
2. 5 Whys: Why did it happen? → Why wasn't it caught? → Why wasn't the alert better?
3. Contributing factors: What enabled the failure?
4. Action items: Preventive measures (with owners and deadlines)
5. Share: Publish RCA to team (blameless culture)
```

---

### Ansible — Role Customization & Secret Management

**Role structure:**
```
roles/
└── webserver/
    ├── tasks/main.yml       ← What to do
    ├── handlers/main.yml    ← Restart services when config changes
    ├── templates/nginx.conf.j2  ← Config templates
    ├── defaults/main.yml    ← Default variables (overridable)
    └── vars/main.yml        ← Fixed variables
```

**Role customization example:**
```yaml
# playbook.yml
- hosts: webservers
  roles:
    - role: webserver
      vars:
        nginx_port: 8080        # Override default port
        ssl_enabled: true       # Enable SSL for this environment
```

**Secret management:**
```bash
# Encrypt sensitive files with Ansible Vault:
ansible-vault encrypt group_vars/prod/secrets.yml
# Edit encrypted file:
ansible-vault edit group_vars/prod/secrets.yml
# Use in playbook (auto-decrypts at runtime):
ansible-playbook site.yml --ask-vault-pass
```

**Best practice:** Use external secret store (AWS Secrets Manager, HashiCorp Vault) and lookup in playbooks:
```yaml
- name: Get DB password from AWS
  set_fact:
    db_password: "{{ lookup('aws_ssm', '/prod/db/password', region='us-east-1') }}"
```

---

### Terraform — Multi-Cloud CI/CD, State Management, Governance

**Multi-cloud CI/CD integration:**
```yaml
# GitHub Actions workflow for Terraform
name: Terraform CI/CD
on:
  push:
    branches: [main]
    paths: ['Terraform/**']
jobs:
  plan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
      - run: terraform init
      - run: terraform plan -out=tfplan
      - uses: actions/upload-artifact@v4
        with: { name: tfplan, path: tfplan }
  apply:
    needs: plan
    environment: production  # Requires manual approval
    steps:
      - run: terraform apply tfplan
```

**Governance:**
- **Sentinel/OPA policies:** Enforce rules like "no public S3 buckets", "all EC2 must have tags"
- **Approval gates:** `terraform apply` only runs after PR approval
- **Cost estimation:** Use `infracost` to show cost impact in PR comments
- **Drift detection:** Scheduled `terraform plan` alerts on unexpected changes

---

### Infrastructure Quality Controls

**Validation:**
```bash
terraform validate        # Syntax check
terraform fmt -check      # Formatting check
tflint                    # Lint rules (naming conventions, best practices)
```

**Security scanning:**
```bash
checkov -d .              # Scan for misconfigurations (open SGs, unencrypted storage)
tfsec .                   # Terraform security scanner
trivy config .            # Vulnerability scan on IaC
```

**Approval workflows:**
```
Developer → PR → terraform plan (automated) → Security scan → Team review → Approve → Apply
```

---

### Configuration Drift — Staging vs Production

**Problem:** Staging works perfectly, production breaks. Why? Because staging and production configs diverged over time.

**Common drift sources:**
- Manual changes in prod console (someone added a SG rule)
- Different variable values not tracked in Git
- Terraform state drift (apply failed partially)
- Different provider versions between environments

**Remediation approach:**
```bash
# 1. Detect drift:
terraform plan -refresh-only  # Shows what changed in cloud vs state

# 2. Compare environments:
diff tfvars/staging/staging.tfvars tfvars/prod/prod.tfvars

# 3. Fix:
# - If drift should be kept: update code to match
# - If drift should revert: terraform apply

# 4. Prevent:
# - Lock console access (read-only for most)
# - All changes through Terraform CI pipeline
# - Same modules for both environments (different variables only)
```

---

### Deployment Strategies — Blue-Green & Rollback Planning

**Blue-Green:**
```
Current (Blue) ←── ALL traffic goes here
New (Green)    ←── Deployed but no traffic

Testing passes:
Current (Blue) ←── Traffic REMOVED
New (Green)    ←── ALL traffic switched here

If problem:
Current (Blue) ←── Traffic switched BACK (instant rollback)
New (Green)    ←── Killed
```

**Implementation in Kubernetes:**
```yaml
# Two deployments running simultaneously
apiVersion: argoproj.io/v1alpha1
kind: Rollout
spec:
  strategy:
    blueGreen:
      activeService: order-service          # Blue (current traffic)
      previewService: order-service-preview  # Green (for testing)
      autoPromotionEnabled: false            # Manual promotion
```

**Rollback planning checklist:**
- ✅ Keep previous image tag in ECR (don't delete old images)
- ✅ Database rollback: migration scripts must be reversible
- ✅ Feature flags: disable new feature without redeploying
- ✅ DNS TTL: keep low (60s) during deployments for fast switch
- ✅ Test rollback regularly (chaos engineering — simulate failure)

---

### Production Support & Real-Time Troubleshooting

**Scenario: Service is down at 2am**

```
2:00 AM - PagerDuty alert: "order-service error rate > 5%"
2:01 AM - Check Grafana: error rate spiking, latency P99 = 30s
2:02 AM - kubectl get pods: order-service-abc CrashLoopBackOff
2:03 AM - kubectl logs order-service-abc --previous:
          "Connection refused: payment-service:5000"
2:04 AM - kubectl get pods -n payment-service: 0/1 Pending
2:05 AM - kubectl describe pod: "Insufficient memory"
2:06 AM - FIX: kubectl scale deployment/payment-service --replicas=1
          Wait... pod starts on different node with more memory
2:08 AM - order-service recovers automatically (retry logic)
2:10 AM - Grafana: error rate back to 0, latency normal
2:11 AM - Update status page: "Resolved"

Next day: Write post-mortem
  Root cause: Node ran out of memory due to monitoring stack growth
  Fix: Add resource quotas, enable cluster autoscaler
```

**Key debugging commands (print and keep handy):**
```bash
# Status overview
kubectl get pods -A | grep -v Running     # Only show problems
kubectl get events -A --sort-by=.lastTimestamp | head -20  # Recent events

# Per-service debug
kubectl describe pod <pod-name> -n <namespace>   # Events + conditions
kubectl logs <pod-name> --previous               # Why it LAST crashed
kubectl top pods -n <namespace>                  # CPU/memory usage

# Node-level
kubectl describe node <node-name> | grep -A5 "Allocated resources"
kubectl top nodes                               # Node resource usage
```
