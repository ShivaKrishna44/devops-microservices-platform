# DevOps Interview Preparation — Simplified with Examples

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

**Configure in Jenkins:** Manage Jenkins → System → Global Pipeline Libraries → Add library (Git URL of the shared lib repo).
----
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
------
## SECTION 1: Terraform Deep-Dive

---

### 1. How does Terraform handle state locking, and what happens if the lock is lost mid-apply?

**Simple explanation:**
Think of state locking like a "Do Not Disturb" sign on a hotel door. When you run `terraform apply`, it puts a lock on the state file so no one else can modify it at the same time.

**Example:**
- You're running `terraform apply` to create an EKS cluster
- Your teammate also runs `terraform apply` at the same time
- Second person gets: `Error: Error locking state`
- This prevents both of you from creating duplicate clusters

**If lock is lost mid-apply (machine crashes, network dies):**
```bash
# You'll see this error next time:
Error: Error locking state: ConditionalCheckFailedException

# Fix: Force unlock (only if you're SURE no one else is running)
terraform force-unlock abc123-lock-id

# Then verify state is okay:
terraform plan
```

**Real example from my project:** We use S3 + DynamoDB for state locking:
```hcl
backend "s3" {
  bucket         = "shivakrishna-tf-state-prod"
  key            = "prod/terraform.tfstate"
  region         = "us-east-1"
  dynamodb_table = "terraform-state-lock-prod"  # This is the lock
  encrypt        = true
}
```

---

### 2. Terraform plan shows no change, but apply still modifies resources — when?

**Simple explanation:**
`plan` checks your code against the STORED state file. But the actual cloud resource might have been changed by someone manually. Plan doesn't always detect this.

**Example:**
1. You create an S3 bucket with Terraform
2. Someone adds encryption manually in AWS console
3. `terraform plan` says "No changes" (because your code + state match)
4. But `terraform apply` with `refresh` detects the console change and tries to revert it

**Another example:**
```hcl
# Your code uses a timestamp
locals {
  deploy_time = timestamp()  # Changes every second!
}
```
Plan shows "no change" for infrastructure, but the timestamp changes on every apply.

**Key takeaway:** Always run `terraform plan -refresh-only` periodically to catch drift.

---

### 3. How do you safely manage Terraform state across multiple teams?

**Simple explanation:**
Imagine 5 people editing the same Google Doc at once without "track changes" — chaos. Same with Terraform state.

**Solution — separate state files per environment:**
```
Team A (dev):   s3://state-bucket/dev/terraform.tfstate
Team B (prod):  s3://state-bucket/prod/terraform.tfstate
```

**Rules I follow:**
- ❌ Never share state between environments
- ❌ Never run `terraform apply` locally for production
- ✅ Only CI/CD pipeline applies to prod
- ✅ Use DynamoDB locking so two pipelines can't apply simultaneously
- ✅ Encrypt state (contains secrets in plain text)

**Example from my project:**
```
Terraform/
├── tfvars/dev/backend.tfvars    → separate state for dev
├── tfvars/prod/backend.tfvars   → separate state for prod
```

---

### 4. What problems arise when multiple modules reference the same resource?

**Simple explanation:**
Imagine two departments both ordering the same office printer. You end up with two printers, or worse — one department cancels the other's order.

**Example problem:**
```hcl
# Module A creates a security group
module "eks" { ... creates sg-abc ... }

# Module B also tries to create the same security group
module "rds" { ... creates sg-abc ... } # CONFLICT!
```

**Solution — one owner, others read:**
```hcl
# Parent module creates the shared resource
resource "aws_security_group" "shared" { ... }

# Both child modules RECEIVE it as input
module "eks" { security_group_id = aws_security_group.shared.id }
module "rds" { security_group_id = aws_security_group.shared.id }
```

---

### 5. count vs for_each — why switching between them destroys resources

**Simple explanation:**

`count` = numbered list (index 0, 1, 2)
`for_each` = named list (key "mysql", "backend", "frontend")

**Example of the problem:**
```hcl
# Original with count:
resource "aws_instance" "server" {
  count = 3  # Creates server[0], server[1], server[2]
}
```

Now remove the MIDDLE server. With count:
- Remove server[1] → server[2] shifts down to become server[1]
- Terraform DESTROYS old server[2] and RECREATES it as server[1]
- You just killed a production server!

**With for_each — safe:**
```hcl
resource "aws_instance" "server" {
  for_each = toset(["mysql", "backend", "frontend"])
}
```
Remove "backend" → only "backend" is destroyed. "mysql" and "frontend" are untouched.

**Rule:** Always use `for_each` for resources you might add/remove. Use `count` only for simple on/off toggles.

---

### 6. How do you handle secrets in Terraform without exposing them in state?

**The ugly truth:** Terraform stores EVERYTHING in state in plain text — including your database passwords.

**Example — the WRONG way:**
```hcl
resource "aws_db_instance" "db" {
  password = "SuperSecret123"  # Stored in state file forever!
}
```

**The RIGHT way — read from AWS Secrets Manager:**
```hcl
data "aws_ssm_parameter" "db_password" {
  name            = "/prod/db/password"
  with_decryption = true
}

resource "aws_db_instance" "db" {
  password = data.aws_ssm_parameter.db_password.value
}
```

**Still in state?** Yes — but at least it's not hardcoded in your Git repo. Protect state with:
- S3 bucket encryption
- IAM policies restricting state access
- Never store state locally

---

### 7. How do you detect and fix infra drift without downtime?

**What is drift?** Someone changes something in AWS console that doesn't match your Terraform code.

**Example:**
1. Your code says security group allows port 443 only
2. Someone manually adds port 8080 in AWS console
3. That's "drift" — reality ≠ code

**Detection:**
```bash
# See what's different between cloud and state:
terraform plan -refresh-only

# Output shows:
# ~ aws_security_group.web
#   ~ ingress = [... port 8080 added ...]
```

**Fix without downtime:**
- If the manual change should STAY: update your .tf code to include port 8080, then `apply`
- If the manual change should GO: just `terraform apply` — it reverts cloud to match code
- Use `-target` to fix one resource without touching others

---

### 8. You delete a resource manually from cloud but not from Terraform — what happens?

**Example:**
1. You have an EC2 instance managed by Terraform
2. You delete it from AWS Console
3. Next `terraform plan`:

```
+ aws_instance.web will be created
```

Terraform says: "Code says this should exist, but I can't find it — I'll create it again."

**If you DON'T want it recreated:**
```bash
# Remove from code (delete the resource block from .tf file)
# AND remove from state:
terraform state rm aws_instance.web
```

Now Terraform forgets it ever existed.

---

### 9. How do you design reusable modules without tight coupling?

**Bad module (tightly coupled):**
```hcl
module "everything" {
  source = "./modules/app"
  # Creates VPC + EKS + RDS + S3 + IAM all together
  # Can't use VPC without EKS!
}
```

**Good module (loosely coupled):**
```hcl
module "vpc" { source = "./modules/vpc" }
module "eks" {
  source = "./modules/eks"
  vpc_id = module.vpc.vpc_id  # Receives VPC as input
}
```

**Rules:**
- One module = one job (VPC module, EKS module, not "everything" module)
- Communicate via inputs/outputs only
- Never hardcode values inside modules
- Provide sensible defaults

---

### 10. depends_on vs implicit dependency — when does Terraform get it wrong?

**Implicit (automatic):**
```hcl
resource "aws_instance" "web" {
  subnet_id = aws_subnet.main.id  # Terraform knows: create subnet first
}
```
Terraform sees the reference → builds the dependency graph automatically.

**Explicit depends_on (manual):**
```hcl
resource "aws_instance" "web" {
  depends_on = [aws_iam_role_policy_attachment.web_policy]
  # No direct reference, but instance needs this policy at boot
}
```

**When Terraform gets it wrong:**
- IAM policies: You create a role and use it immediately. AWS takes 10 seconds to propagate IAM. Terraform doesn't know to wait.
- EKS addons: Addon needs OIDC provider to exist, but no direct attribute reference between them.

**Fix:** Add explicit `depends_on` when you know there's a hidden dependency.

---

### 11. How do workspaces work, and why are they dangerous?

**How they work:**
```bash
terraform workspace new dev     # Creates dev workspace
terraform workspace new prod    # Creates prod workspace
terraform workspace select dev  # Switch to dev

# Same code, different state files:
# .terraform.tfstate.d/dev/terraform.tfstate
# .terraform.tfstate.d/prod/terraform.tfstate
```

**Why they're dangerous in large teams:**
- One typo in code affects ALL environments (dev AND prod use same files)
- Easy to forget which workspace you're in: `terraform apply` → accidentally modified prod
- Can't have different PR reviews for dev vs prod changes

**Better approach:**
```
environments/
├── dev/    → own code, own state, own CI pipeline
├── prod/   → own code, own state, own CI pipeline
modules/    → shared reusable modules
```

---

### 12. How do you refactor Terraform without destroying production?

**Example:** Moving a resource into a module.

Before: `aws_instance.web` (in root)
After: `module.compute.aws_instance.web` (inside module)

**Wrong way:** Just move the code → Terraform destroys old + creates new (DOWNTIME!)

**Right way:**
```bash
# 1. Move in state (tells Terraform "this is the same resource, new address")
terraform state mv aws_instance.web module.compute.aws_instance.web

# 2. Move in code (put the resource block inside the module)

# 3. Verify
terraform plan
# Should show: "No changes" ✅
```

---

### 13. What are partial applies and how to recover?

**Example:**
You're creating 10 resources. Resource #7 fails (wrong AMI ID).
- Resources 1-6: created successfully ✅
- Resource 7: failed ❌
- Resources 8-10: never attempted

**State is accurate** — it knows 1-6 exist, 7-10 don't.

**Recovery:**
1. Fix the AMI ID in your code
2. Run `terraform apply` again
3. Resources 1-6: no change (already exist)
4. Resource 7-10: created now ✅

Terraform is idempotent — re-running apply is always safe.

---

### 14. How do provider version mismatches break production?

**Example:**
- You wrote code with AWS provider v5.x
- Provider v6.x renames an attribute from `instance_type` to `instance_size`
- Upgrade provider → `terraform plan` wants to DESTROY and RECREATE all instances

**Prevention:**
```hcl
# Pin the version:
required_providers {
  aws = {
    source  = "hashicorp/aws"
    version = "~> 6.0"  # Allows 6.1, 6.2 but NOT 7.0
  }
}
```

And commit `.terraform.lock.hcl` — this pins the exact hash of the provider binary.

**Real example from my project:** Lock file had provider 5.x but the installed binary was 6.51.0. Had to update the version constraint from `~> 5.95` to `~> 6.0` to match.

---

## SECTION 2: Scenario-Based Questions (Pressure Tests)

---

### 1. Deployment succeeded but traffic still goes to old version — where to debug?

**Think of it like a highway:** Code deployed (car is on the road) but GPS (DNS/Ingress) still points to the old route.

**Check in order:**
```bash
# 1. Are new pods running?
kubectl get pods -l app=order-service
# Look for: new pods Running, old pods Terminating

# 2. Does the Service point to new pods?
kubectl get endpoints order-service
# Should show IP addresses of NEW pods

# 3. Does Ingress point to correct Service?
kubectl describe ingress app-ingress
# Check backend: order-service:5000

# 4. Is DNS pointing to correct ALB?
nslookup app.vosukula.online
# Should resolve to current ALB
```

**Most common cause:** Old ReplicaSet still running because `maxUnavailable: 0` means both old and new run simultaneously, and service selector matches both.

---

### 2. Pods show healthy but users get 504 errors — troubleshooting flow

**504 = ALB waited too long for a response from the pod.**

Think of it like: ALB rings the doorbell (sends request), waits 30 seconds, nobody answers → gives up → tells user "504".

**Debug path:**
```bash
# 1. Is the pod actually responding?
kubectl exec -it order-service-abc -- curl localhost:5000
# If this hangs → app is stuck (not an infra issue)

# 2. Is readiness probe passing?
kubectl describe pod order-service-abc | grep -A5 Readiness
# If failing → pod removed from service endpoints → ALB has no healthy targets

# 3. Check ALB target health
aws elbv2 describe-target-health --target-group-arn <arn>
# Look for: "unhealthy" targets

# 4. Check if it's a timeout issue
kubectl logs order-service-abc
# Look for slow database queries, connection timeouts
```

---

### 3. AWS bill spiked 3x overnight — no deployments happened

**Step 1:** AWS Cost Explorer → filter by service → sort by cost increase

**Common surprise culprits:**
| Service | Why It Spiked |
|---|---|
| NAT Gateway | A pod started downloading huge files (pulling Docker images repeatedly) |
| EBS | Snapshots accumulating — never cleaned up |
| Data Transfer | Cross-region replication accidentally enabled |
| EC2 | Auto Scaling scaled to max due to a stuck health check |

**Real example:** NAT Gateway costs $0.045/GB of data processed. If your monitoring stack starts scraping 100 pods every 15 seconds and logs are being shipped cross-AZ — that's terabytes of NAT traffic.

**Fix:** Set AWS Budget alerts: "Alert me if daily spend exceeds $50."

---

### 4. CI/CD pipeline takes 40+ minutes — CTO wants under 10

**Where time goes (typical):**
```
Git clone:              30 sec
Install dependencies:   5 min    ← CACHE THIS
Docker build:          10 min    ← LAYER CACHING
Docker push:            3 min    ← can't speed up much
Tests:                  8 min    ← RUN IN PARALLEL
Deploy:                 5 min    ← can't speed up much
Waiting/scheduling:     8 min    ← FIX AGENT AVAILABILITY
```

**Fixes:**
1. Docker layer caching: `docker build --cache-from previous-image` → saves 7 min
2. Parallel testing: run unit + lint + security scan simultaneously → saves 5 min
3. Pre-built agent image: bake docker, kubectl, helm into agent → saves 3 min
4. Shallow git clone: `git clone --depth 1` → saves 1 min
5. Skip unchanged services: if only `order-service` changed, don't build the other two

**Result:** 40 min → 8 min without adding hardware.

---

### 5. SRE says infra stable, dev says slow, monitoring shows GREEN — who to believe?

**Always believe the user.** If monitoring says green but users experience slowness — your monitoring is wrong, not the user.

**What's missing from your monitoring:**
```
✅ You monitor: CPU 20%, Memory 40%, Pods Running
❌ You DON'T monitor: p99 latency, DNS resolution time, connection pool wait time
```

**Example:** Average response time is 100ms (looks good). But p99 is 5 seconds — meaning 1% of users wait 5 seconds. Average hides the problem.

**Fix:** Add application-level metrics:
```python
# In your Flask app
from prometheus_client import Histogram
REQUEST_LATENCY = Histogram('request_latency_seconds', 'Request latency')
```

---

### 6. Terraform apply failing due to drift, but infra is live and critical

**Scenario:** Someone manually added a security group rule in AWS console. Now `terraform apply` wants to remove it. But that rule is keeping production alive!

**Safe approach:**
```bash
# 1. See what drifted (DON'T apply yet):
terraform plan -refresh-only

# 2. Understand the drift:
# Output: "~ security_group will remove rule for port 8080"
# Decision: Do we NEED port 8080? Yes? Then update code.

# 3. Update code to match reality:
# Add the port 8080 rule to your .tf file

# 4. Now plan shows no changes:
terraform plan  # "No changes. Infrastructure is up-to-date."

# 5. Apply safely — nothing changes in cloud
terraform apply
```

**Rule:** Never run `terraform apply` on drifted prod without understanding every change in the plan output.

---

### 7. Rollback script fails during outage — 5 min before SLA breach

**This is about DECISION MAKING, not tools.**

```
Minute 0:   Outage detected. New deployment broke something.
Minute 1:   Run rollback script → FAILS (image not found, permission error)
Minute 2:   DECISION: Don't waste time debugging the script.
            Manual rollback: kubectl rollout undo deployment/order-service
Minute 3:   If that fails too → scale up the PREVIOUS version manually:
            kubectl scale deployment/order-service-v1 --replicas=3
Minute 4:   If nothing works → DNS failover to maintenance page
Minute 5:   Service restored (even if ugly). SLA saved.
```

**After the fire:** Fix the rollback script, write postmortem, add the scenario to runbooks.

**Key principle:** During outage → RESTORE FIRST, DEBUG LATER. Any action that brings service back is correct.

---

### 8. Secret committed to GitHub — already cloned by others

**Order matters — do this EXACTLY:**

1. **ROTATE THE SECRET NOW** (don't investigate first)
   ```bash
   # If it's an AWS key:
   aws iam delete-access-key --access-key-id AKIAXXXXXXX --user-name admin
   # Create new key
   aws iam create-access-key --user-name admin
   ```

2. **Check if it was used by an attacker:**
   ```bash
   aws cloudtrail lookup-events --lookup-attributes AttributeKey=AccessKeyId,AttributeValue=AKIAXXXXXXX
   ```

3. **Remove from Git history:**
   ```bash
   # Install BFG Repo Cleaner (faster than filter-branch)
   bfg --delete-files .env
   git push --force
   ```

4. **Notify team** — everyone who cloned has it locally

5. **Prevent next time:**
   - Add `.env` to `.gitignore`
   - Install `git-secrets` pre-commit hook
   - Use AWS Secrets Manager instead of files

---

### 9. K8s cluster upgrade works in staging but corrupts CoreDNS in production

**Why it happened:** Production has custom CoreDNS ConfigMap (custom forwarding rules). The upgrade overwrote it with defaults.

**Immediate fix:**
```bash
# 1. Check CoreDNS status
kubectl get pods -n kube-system -l k8s-app=kube-dns
# If CrashLoopBackOff → ConfigMap is broken

# 2. Restore the known-good ConfigMap
kubectl apply -f backup/coredns-configmap.yaml

# 3. Restart CoreDNS
kubectl rollout restart deployment/coredns -n kube-system

# 4. Verify DNS works
kubectl run dns-test --image=busybox --rm -it -- nslookup kubernetes.default
```

**Prevention:** Before ANY cluster upgrade:
- Backup all ConfigMaps in kube-system
- Test DNS resolution as validation step
- Upgrade one node at a time (canary nodes)

---

### 10. Tell me a real scenario where YOU introduced a failure

**Your answer (from this project):**

"I configured Jenkins Helm values to use `existingSecret: jenkins-admin-secret` for the admin password — but I forgot to create that Kubernetes secret before running the Helm install.

The Jenkins pod was stuck in `Init:0/2` for over 50 minutes. I kept checking pod status, Helm releases, and ingress — but the actual error was only visible in `kubectl describe pod` → Events section: `MountVolume.SetUp failed for volume jenkins-secrets: secret not found`.

**What I learned:**
- Always check Events in `kubectl describe` — not just status
- Prerequisites (secrets, PVCs, ConfigMaps) must exist BEFORE the Helm install
- Added a checklist in my deployment guide: 'Create secrets first'

**What changed:**
- Deployment guide now has prerequisite steps clearly marked
- Install scripts validate secret existence before proceeding"

---

## SECTION 3: Real DevOps Questions (Simplified)

---

### 1. What happens when a pod gets OOMKilled?

**Simple analogy:** You give a container 256MB memory limit. It tries to use 260MB. Linux kernel says "NOPE" and kills it immediately — no warning, no graceful shutdown.

```bash
# You see this:
kubectl get pods
# NAME          READY   STATUS      RESTARTS
# order-svc     0/1     OOMKilled   5

# Check what happened:
kubectl describe pod order-svc
# Last State: Terminated
# Reason: OOMKilled
# Exit Code: 137 (= 128 + 9, SIGKILL)
```

**Fix:** Either increase memory limit or fix the memory leak in the app.

---

### 2. Pipeline works in staging but fails in prod with "permission denied"

**Most common cause:** Different IAM roles between staging and prod.

**Debugging:**
```bash
# On the agent running the pipeline:
aws sts get-caller-identity
# Shows WHICH role the pipeline is using

# Compare staging role permissions vs prod role permissions
# Usually prod has stricter IAM policies
```

**Example:** Staging role has `AdministratorAccess`, prod role only has `AmazonEKSClusterPolicy`. Pipeline needs ECR push permission which prod role doesn't have.

---

### 3. How does Kubernetes DNS work across namespaces?

**Simple rule:**
- Same namespace: just use service name → `order-service`
- Different namespace: use `<service>.<namespace>` → `order-service.production`
- Full name: `order-service.production.svc.cluster.local`

**What breaks it:**
- CoreDNS pods crash → ALL DNS fails cluster-wide
- NetworkPolicy blocks port 53 → pods can't reach CoreDNS
- Someone edits CoreDNS ConfigMap with a typo

---

### 4. Terraform state lock is stuck — how to recover?

```bash
# Step 1: Confirm no one else is running apply (ask your team!)
# Step 2: Force unlock
terraform force-unlock 12345-abcde-lock-id
# Step 3: Verify
terraform plan  # Should work now
```

**Never force-unlock without asking.** Maybe a colleague's laptop died mid-apply and they'll restart.

---

### 5. How do you design observability for high-scale systems?

**Three pillars — each answers a different question:**

| Pillar | Question It Answers | Tool |
|---|---|---|
| Metrics | "Is the system healthy RIGHT NOW?" | Prometheus |
| Logs | "WHAT happened at 3:47am?" | ELK / Loki |
| Traces | "WHERE did this request get slow?" | Jaeger / OpenTelemetry |

**Example:** User reports slow checkout.
1. Metrics show: p99 latency spiked at 3:47am
2. Traces show: request spent 4 seconds in payment-service
3. Logs show: payment-service connection timeout to database

---

### 6. Secret exposed in GitHub — incident response plan?

```
Second 0:  ROTATE the secret (don't wait, don't investigate first)
Minute 1:  Check CloudTrail — was it used by anyone unauthorized?
Minute 5:  Remove from Git history (BFG Repo Cleaner)
Minute 10: Force push cleaned history
Minute 15: Notify team + add pre-commit hook to prevent recurrence
```

---

### 7. How does HPA (Horizontal Pod Autoscaler) work internally?

**Simple flow:**
```
Metrics Server checks pods every 15 seconds
    ↓
HPA Controller compares: current CPU 90% vs target 70%
    ↓
Calculates: need more pods! (90/70 × 2 pods = 3 pods needed)
    ↓
Scales deployment from 2 → 3 replicas
    ↓
Waits 3 minutes before scaling up again (cooldown)
```

**Example from my project:**
```yaml
autoscaling:
  enabled: true
  minReplicas: 1
  maxReplicas: 5
  targetCPUUtilization: 70  # Scale up when CPU > 70%
```

---

### 8. What is error budget & burn rate in SRE?

**Error budget — simple math:**
- SLO: 99.9% uptime
- That means 0.1% allowed downtime
- Per month: 0.1% × 30 days × 24h × 60min = **43 minutes of allowed downtime**

**Burn rate:**
- Rate 1x = using budget at sustainable pace (43 min spread over 30 days)
- Rate 10x = using 10 days of budget in 1 day → ALERT! Stop deploying!
- Rate 0.1x = very healthy, lots of budget left → ship faster!

**How it works in practice:** If your team burns through the error budget → deployment freeze until budget recovers. This makes reliability a shared responsibility.

---

### 9. Service has latency spikes every 60 seconds — how to debug?

**Regular intervals = something SCHEDULED is causing it.**

**Check these (in order):**
1. Kubernetes liveness probe hitting heavy endpoint every 60s?
2. CronJob running every minute?
3. Prometheus scraping expensive `/metrics` endpoint every 60s?
4. Garbage collection (Java GC pauses)?
5. Log rotation running every minute?
6. DNS TTL = 60s causing re-resolution spike?

**Debug:** Run `kubectl exec -it pod -- top` DURING the spike to see what process is consuming resources.

---

### 10. Push vs Pull CD — how does GitOps (ArgoCD) work?

**Push (Jenkins):**
```
Jenkins → "Hey cluster, here's the new version" → kubectl apply
```
- Jenkins needs cluster credentials
- If someone manually changes the cluster → stays changed (no self-heal)

**Pull (ArgoCD — GitOps):**
```
ArgoCD (inside cluster) → watches Git every 3 min → "Is Git different from cluster?"
                        → YES → auto-sync cluster to match Git
```
- No credentials stored outside cluster
- Manual changes get REVERTED automatically (self-healing)
- Git = single source of truth

---

### 11. Dockerfile best practices for security and performance?

**Security:**
```dockerfile
# ✅ Good
FROM python:3.11-slim              # Minimal base image
RUN adduser --disabled-password appuser  # Non-root user
USER appuser                        # Run as non-root
COPY requirements.txt .             # Specific files only

# ❌ Bad
FROM python:3.11                   # Full image (900MB vs 120MB)
# No USER directive → runs as root
COPY . .                           # Copies .env, .git, secrets!
```

**Performance:**
```dockerfile
# ✅ Order layers by change frequency (cache optimization)
COPY requirements.txt .             # Changes rarely → cached
RUN pip install -r requirements.txt # Cached if requirements unchanged
COPY . .                           # Changes often → last layer
```

---

### 12. What is Platform Engineering and how would you design an IDP?

**Simple explanation:** Building a "developer vending machine" — developers press buttons, get infrastructure/deployments without needing to understand Terraform or Kubernetes.

**Example:**
- Developer wants new service → fills a form in Backstage → gets Git repo + CI pipeline + Helm chart + monitoring automatically
- Developer wants to deploy → pushes code → GitOps handles everything
- Developer wants database → selects "PostgreSQL" from catalog → gets an RDS instance with proper backups

**My design:**
1. Backstage (portal) → developers interact here
2. Terraform modules (building blocks) → create infra on demand
3. Helm chart templates → deploy services automatically
4. ArgoCD (deployment) → GitOps sync
5. Kyverno (guardrails) → enforce standards (resource limits, labels, security)

---

## SECTION 4: Monitoring Deep-Dive (Simplified)

---

### 1. End-to-end monitoring strategy — what layers do you monitor?

```
Layer 5: BUSINESS    → Orders/sec, revenue, signup rate
Layer 4: APPLICATION → Latency, errors, request rate (Golden Signals)
Layer 3: KUBERNETES  → Pod restarts, scheduling failures, node health
Layer 2: INFRA       → CPU, memory, disk, network
Layer 1: NETWORK     → DNS, inter-service latency, packet loss
```

**Example:** If orders/sec drops (Layer 5) → check application errors (Layer 4) → check pod restarts (Layer 3) → check node memory (Layer 2)

---

### 2. Proactive vs reactive monitoring

**Reactive:** "Error rate hit 5% → alert → engineer investigates." Users already affected.

**Proactive:** "Error rate increasing 2x every 5 minutes → alert BEFORE it hits 5%." Users not yet affected.

**How to be proactive:**
- Monitor TRENDS, not just thresholds
- Synthetic monitoring: fake user requests every 30 seconds
- Alert on leading indicators: "Connection pool 80% full" → means errors coming soon

---

### 3. White-box vs black-box monitoring

**White-box:** Looking INSIDE the system (application metrics, code-level traces)
- "CPU is 90%, database queries taking 3 seconds"

**Black-box:** Looking FROM OUTSIDE (synthetic user checks)
- "Homepage loads in 2 seconds from New York" or "Homepage is DOWN"

**When to use which:**
- Black-box: SLA tracking, "is the site up?" — catches problems you didn't think to monitor internally
- White-box: Debugging, "why is it slow?" — tells you the root cause

---

### 4. How to design alerts that don't cause alert fatigue?

**Bad alerts:**
- "CPU > 50%" → fires every day, nobody acts on it → gets ignored
- 1000 pods each sending "container restarted" → inbox flooded

**Good alerts:**
- Alert on SYMPTOMS: "Error rate > 1% for 5 minutes" (users affected)
- NOT on causes: "CPU > 80%" (might be a batch job, perfectly fine)
- Require DURATION: must stay breached for 5 minutes (avoids flapping)
- Every alert has a RUNBOOK: what to check, who owns it, expected action
- Severity levels: P1 pages on-call, P2 goes to Slack, P3 creates ticket

---

### 5. SLO, SLA, SLI — simple explanation

| Term | What It Is | Example |
|---|---|---|
| SLI | The measurement | "99.2% of requests succeeded this month" |
| SLO | The target | "We aim for 99.9% request success rate" |
| SLA | The contract | "If uptime drops below 99.5%, we refund 10% of the bill" |

**Relationship:** SLI measures reality. SLO is your internal goal. SLA is the promise to customers (always lower than SLO to give you buffer).

---

### 13. How do you handle high cardinality in Prometheus?

**The problem:** Someone adds `user_id` as a metric label. 1 million users × 10 metrics = 10 million time series. Prometheus explodes.

**Rules:**
- ❌ Never use: user IDs, request IDs, IP addresses as labels
- ✅ Use: service name, HTTP method, status code, namespace

**If you need high cardinality:** Log it (Loki/ELK), don't metric it. Metrics = low cardinality aggregates. Logs = high cardinality details.

---

### 14. Distributed tracing — when is it critical?

**When you NEED it:** Microservices architecture. A request goes through 5+ services. One is slow. Which one?

**Without tracing:** "Something is slow somewhere" 🤷

**With tracing (Jaeger/OpenTelemetry):**
```
Request → API Gateway (5ms) → Order Service (10ms) → Payment Service (3000ms!) → Database (2ms)
```
Instantly shows: Payment Service is the bottleneck.

---

### 19. Push-based vs pull-based monitoring

**Pull (Prometheus):**
- Prometheus ASKS each service: "What are your metrics?" (scrapes /metrics endpoint)
- Like a teacher calling each student's name for attendance

**Push (StatsD/Datadog):**
- Each service SENDS metrics to the collector
- Like students raising their hand to say "I'm here"

**Which is better?**
- Pull: easier to know if a service is DOWN (it stops responding to scrape)
- Push: better for short-lived jobs (Lambda functions that only exist for 3 seconds)
- Most use: Pull (Prometheus) for long-running services + Pushgateway for batch jobs

---

### 20. How do you decide what NOT to monitor?

**Don't monitor if:**
- Nobody would act on the alert
- The metric can be calculated from existing metrics
- It's a low-level detail that doesn't affect users
- High-cardinality labels that blow up storage

**Example:** Don't alert on "container restarted once" — Kubernetes handles this. DO alert on "container restarted 5+ times in 10 minutes" — something is fundamentally wrong.

---

## SECTION 5: AWS Architecture Scenarios

---

### 1. High-traffic app lagging during peak hours

**Diagnosis checklist:**
```
CloudWatch → CPU/Memory on EC2 instances (is compute the bottleneck?)
ALB → Target health + 5XX count (are backends failing?)
RDS → Connections + Read IOPS (is database the bottleneck?)
ElastiCache → Hit rate (is cache effective?)
```

**Solutions (depending on bottleneck):**
| Bottleneck | Fix |
|---|---|
| Compute | Auto Scaling + predictive scaling (scale BEFORE peak) |
| Database | Read replicas + ElastiCache + connection pooling (RDS Proxy) |
| Network | CloudFront CDN for static assets (80% of traffic) |
| Cold starts | Minimum instances in ASG, pre-warm Lambda |

---

### 2. On-prem to AWS migration with minimal downtime

**Strategy: "Stranger Fig" pattern** — new AWS infra grows around old on-prem, then cut over.

```
Phase 1: AWS Direct Connect (secure link between on-prem and AWS)
Phase 2: DMS (Database Migration Service) → continuous replication to RDS
Phase 3: Migrate compute (CloudEndure / VMs to EC2)
Phase 4: Route53 weighted routing → shift 10% → 50% → 100% traffic to AWS
Phase 5: Decommission on-prem (keep for 48h rollback window)
```

**Key insight:** Database is always the hardest part. DMS keeps it synced until cutover.

---

### 4. Cost-optimized storage architecture

**S3 lifecycle — money-saving autopilot:**
```
Day 0-30:   Standard ($0.023/GB)
Day 30-90:  Infrequent Access ($0.0125/GB) → 46% savings
Day 90-365: Glacier ($0.004/GB) → 83% savings
Day 365+:   Deep Archive ($0.00099/GB) → 96% savings
```

**Quick wins:**
- Delete orphan EBS volumes (check monthly with Lambda)
- Delete old snapshots (keep last 7 only)
- Use gp3 instead of gp2 (20% cheaper, better performance)
- Compress data before storing (Parquet > CSV — 10x smaller)

---

### 5. Designing for 99.99% uptime (52 min downtime per YEAR)

**Architecture:**
```
Route53 (health checks + failover) → ALB (multi-AZ) → EKS (nodes in 2+ AZs)
                                                        → RDS Multi-AZ (auto-failover)
                                                        → ElastiCache (cluster mode)
```

**Key components:**
- Multi-AZ everything (if one AZ dies, other AZ takes over)
- Auto Scaling (handle load spikes without human intervention)
- Health checks at every level (Route53, ALB, K8s probes)
- Decoupled services (SQS between services — one failing doesn't cascade)
- IaC (Terraform) — can recreate entire environment in another region in 30 min

---

## SECTION 6: Experience-Based (Use YOUR Real Project)

---

### 1. Last production outage handled?

"Jenkins agent kept going offline mid-build. Root cause: EC2 agent had only 727MB free disk. Jenkins marks agents offline when free space drops below 1GB. Docker images were accumulating on the agent.

Fix: Expanded LVM volume with `lvextend`, pruned Docker images, lowered Jenkins disk threshold to 100MB. Added `docker system prune -af` to a weekly cron."

### 2. Deployment failure you debugged recently?

"ECR push failed with 'image tag latest already exists and cannot be overwritten'. Our ECR repos were configured as IMMUTABLE (good for security) but the Jenkinsfile was always pushing a `:latest` tag alongside the version tag. Second push fails because you can't overwrite immutable tags. Fixed by removing the `:latest` push — only unique version tags now."

### 4. Last Terraform issue you fixed?

"409 ResourceInUseException on EKS access entry. The `enable_cluster_creator_admin_permissions = true` flag auto-creates an access entry for the calling identity. We ALSO had the same identity in `access_entries` block. Terraform tried to create a duplicate — AWS rejected it. Removed the explicit entry since the flag handles it."

### 5. How did you reduce infrastructure cost?

"Reduced EKS node replicas from 2 per service to 1 for dev environment (3 services × 2 = 6 pods → 3 pods). Added HPA so production can auto-scale up when needed. Also configured ECR lifecycle policies to keep only last 10 images per repo — prevents unbounded storage costs."

### 7. Which CI/CD failure took longest to debug?

"Jenkins pod stuck in `Init:0/2` for 50+ minutes. Pod status showed 'Initializing' — no error visible. Only `kubectl describe pod` → Events section revealed: `MountVolume.SetUp failed: secret jenkins-admin-secret not found`. The Helm values referenced a secret that was never created. Took long because I was looking at pod logs, Helm status, ingress — not the pod Events."

### 8. Scaling issue in Kubernetes?

"Deployed monitoring stack (Prometheus + Grafana + Alertmanager) alongside Jenkins and 3 microservices on 2× t3.medium nodes. Nodes hit 74% CPU allocation. New pods stayed Pending indefinitely — no room. Fixed by reducing replica count to 1 for non-critical services in dev, and configured node auto-scaling group to max 3 nodes for production."

### 9. One mistake in production and what you learned?

"Pinned VPC module to `?ref=v3.0.0` — a Git tag that didn't exist. Terraform init failed, blocking ALL infrastructure changes until I reverted. Learned: always verify Git refs exist (`git ls-remote`) before changing module sources. Added this as a pre-commit check."

### 10. If I join your project today, what would you improve first?

"Three things:
1. Add network policies between namespaces — currently any pod can talk to any other pod
2. Move from kubectl-created secrets to AWS Secrets Manager with External Secrets Operator
3. Add a pre-deployment validation stage that runs `helm template` + `kubeval` to catch manifest errors before deploy"

---

## Quick Reference Card (Print This)

| Topic | One-Line Answer |
|---|---|
| State locking | DynamoDB prevents two people from applying at once |
| Drift | Reality ≠ code. Detect with `plan`, fix with `apply` or code update |
| count vs for_each | for_each uses stable keys, count uses fragile indices |
| Secrets in state | Always encrypted, always restricted access, never local state |
| OOMKilled | Container exceeded memory limit → kernel kills it → exit code 137 |
| 504 error | ALB timeout → backend not responding → check pod readiness/app health |
| GitOps | Git is truth. ArgoCD syncs cluster to match Git automatically |
| HPA | Metrics Server → HPA Controller → scale replicas based on CPU/memory |
| Error budget | 99.9% SLO = 43 min allowed downtime/month. Burned = freeze deploys |
| Push vs Pull CD | Push = Jenkins applies. Pull = ArgoCD watches Git and self-syncs |


---

## SECTION 7: AWS Scenario-Based Questions (10 Real-World)

---

### 1. EC2 traffic is suddenly high and server is crashing

**Scenario:** High traffic causing high CPU, application becomes unresponsive.

**What to do:**
- Enable Auto Scaling Group to handle traffic spikes (scale from 2 → 5 instances)
- Put ALB in front to distribute load across instances
- Monitor with CloudWatch — set alarm for CPU > 80%
- Optimize application (caching, connection pooling)
- Choose right instance type (compute-optimized for CPU-heavy apps)

**Example:**
```
Before: Single EC2 → gets 10,000 requests → CPU 100% → crashes
After:  ALB → ASG (2-5 instances) → each handles 2,000 requests → healthy
```

---

### 2. RDS database performance is very slow

**Scenario:** Users complaining about slow application due to database.

**What to do:**
- Check CloudWatch: CPU, Disk I/O, Memory, connections
- Enable Performance Insights (shows which queries are slow)
- Optimize slow queries (add indexes, rewrite queries)
- Scale up instance size or switch to Aurora (5x faster than MySQL)
- Add Read Replicas for read-heavy workloads
- Use ElastiCache (Redis) for frequently accessed data

**Example:**
```
Problem: SELECT * FROM orders WHERE user_id = 123 → takes 5 seconds (full table scan)
Fix: CREATE INDEX idx_user_id ON orders(user_id) → now takes 5ms
```

---

### 3. Auto Scaling is NOT scaling out even though CPU is high

**Scenario:** CPU at 80% but ASG not launching new instances.

**What to do:**
- Check Scaling Policy — is it configured? (might be missing or disabled)
- Verify CloudWatch Alarm — is it in ALARM state?
- Check ASG capacity limits — `max_size` might already be reached
- Review instance health checks — if unhealthy, ASG terminates instead of scaling
- Check for dependency limits (Service Quotas — max instances per region)

**Example:**
```
ASG config: min=1, max=2, desired=2
CPU at 90% but can't scale because max=2 already reached!
Fix: Increase max_size to 5
```

---

### 4. Users unable to upload files to S3 — "Access Denied"

**Scenario:** Application throws "Access Denied" error when trying to upload.

**What to do (check in order):**
1. Check IAM permissions — does the role have `s3:PutObject`?
2. Verify bucket policy — is it allowing the caller?
3. Check ACL and Object Ownership settings
4. Ensure correct Region — bucket might be in different region
5. Check if any SCP (Service Control Policy) is blocking at org level

**Example:**
```json
// Missing this in IAM policy:
{
  "Effect": "Allow",
  "Action": "s3:PutObject",
  "Resource": "arn:aws:s3:::my-bucket/*"
}
```

---

### 5. Application not accessible from internet even though EC2 is running

**Scenario:** EC2 instance running, but users can't access the application.

**What to do:**
- Check Security Group — is inbound port (80/443) open?
- Check NACL — is subnet-level firewall blocking?
- Verify Route Table — does subnet have internet gateway route?
- Ensure ALB/instance is in public subnet with public IP
- Check OS-level firewall (iptables/firewalld)

**Example from my project:**
```
Jenkins on EC2 was running (systemctl status = active)
But port 8080 wasn't reachable
Root cause: Security group didn't have port 8080 inbound rule
Fix: Added inbound rule TCP 8080 from 0.0.0.0/0
```

---

### 6. Route53 domain is not resolving

**Scenario:** DNS records configured but domain still not resolving.

**What to do:**
- Check if hosted zone is correct (public vs private)
- Verify DNS record type (A/AAAA/CNAME) matches expectation
- Check TTL — old record might be cached (wait for TTL to expire)
- Use DNS checker tools: `nslookup`, `dig`
- Ensure name servers are correct (NS records at registrar match Route53)

**Example from my project:**
```
jenkins.vosukula.online had a CNAME pointing to old ALB
Terraform tried to create an A record → CONFLICT
Route53 doesn't allow A + CNAME with same name
Fix: Deleted old CNAME, let ALB controller create new one
```

---

### 7. EBS volume running out of space — application failing

**Scenario:** EC2 disk is full, application can't write logs/data.

**What to do:**
- Free up space: `docker system prune -af`, clean logs
- Increase EBS volume size (online, no downtime): modify volume → extend filesystem
- Add CloudWatch alarm for disk usage > 80%
- Use EBS auto-snapshot for backup before expanding

**Example from my project:**
```bash
# Jenkins agent had 727MB free → Jenkins marked it offline
# Fix:
sudo growpart /dev/nvme0n1 4
sudo lvextend -l +100%FREE /dev/mapper/RootVG-homeVol
sudo xfs_growfs /home
# Result: 20GB free
```

---

### 8. ALB health checks failing for some instances — intermittent errors

**Scenario:** Some targets showing unhealthy in target group.

**What to do:**
- Check Target Group health check path — does it return 200?
- Verify health check port matches application port
- Check instance logs for errors
- Ensure Security Group allows ALB to reach the instance
- Increase health check timeout/interval if app is slow to start

**Example:**
```
Health check path: /login (Jenkins)
New pod takes 3 minutes to start → health check fails during startup
Fix: Set initialDelaySeconds: 60 in readiness probe
```

---

### 9. Securing your application and data (network and access)

**What to do:**
- Apply least privilege IAM policies (no `*` permissions)
- Use private subnets for application, public only for ALB
- Security Groups: restrict by source (not 0.0.0.0/0 for SSH)
- Enable encryption: EBS (KMS), S3 (SSE), RDS (encryption at rest)
- Enable CloudTrail and GuardDuty for threat detection
- Use ACM certificates for HTTPS

**Example from my project:**
```hcl
# EBS encryption on Jenkins agent
root_block_device {
  volume_size = 50
  encrypted   = true  # Data at rest encrypted with KMS
}
```

---

### 10. Highly available and disaster recovery solution

**Scenario:** Business continuity — ensure service survives AZ or region failure.

**Architecture:**
```
Primary Region (us-east-1):
  - Multi-AZ RDS (auto-failover)
  - EKS nodes across 2 AZs
  - ALB routing to healthy AZs
  - S3 Cross-Region Replication → DR region

DR Region (us-west-2):
  - Route53 failover routing
  - Read Replica promoted to primary if needed
  - Same Terraform code → spin up in 30 min
```

**Key components:**
- Route53 health checks → auto-failover to DR
- RDS Multi-AZ → automatic database failover (30 seconds)
- S3 CRR → data replicated to DR region
- Create backups and test DR plan quarterly

---

## SECTION 8: CI/CD & DevOps Practice Questions

---

### 1. Explain CI/CD pipeline process from code commit to production deployment

**My pipeline (with example):**
```
Developer pushes code to GitHub
    ↓
Jenkins detects change (webhook or poll)
    ↓
Stage 1: Checkout code from Git
    ↓
Stage 2: Build & Test (parallel)
    ↓
Stage 3: SonarQube scan (quality gate)
    ↓
Stage 4: Docker build → tag → push to ECR
    ↓
Stage 5: Deploy to EKS
    Option A: kubectl apply (direct)
    Option B: helm upgrade (packaged)
    Option C: update Git tag → ArgoCD auto-syncs (GitOps)
    ↓
Post: Notify success/failure
```

---

### 2. Common failure points in CI/CD pipeline and how to address them

| Failure Point | Example | Fix |
|---|---|---|
| Flaky tests | Test passes sometimes, fails randomly | Isolate tests, mock external services |
| Docker build timeout | Large image, slow network | Layer caching, slim base images |
| Permission denied | Different IAM between envs | Standardize roles, test in staging first |
| Registry push fails | Network timeout, auth expired | Retry logic, refresh ECR token before push |
| Deploy fails | Missing ConfigMap, wrong image tag | Pre-deploy validation, helm template + kubeval |
| Agent offline | Disk full, network issue | Monitor agents, auto-reconnect scripts |

---

### 3. How do you manage multi-cloud infrastructure using Terraform?

**Approach:** Same Terraform structure, different providers.

```hcl
# providers.tf
provider "aws" {
  region = "us-east-1"
  alias  = "aws"
}

provider "azurerm" {
  features {}
  alias = "azure"
}

# Use provider aliases in resources
resource "aws_instance" "web" {
  provider = aws.aws
}

resource "azurerm_virtual_machine" "web" {
  provider = azurerm.azure
}
```

**Key principles:**
- Separate state per cloud (don't mix AWS + Azure state)
- Use modules per cloud (aws-vpc module, azure-vnet module)
- Abstract common logic (variables for region, instance size mapping)

---

### 4. Terraform state management in multi-cloud projects

**One state per environment per cloud:**
```
s3://state-bucket/aws/dev/terraform.tfstate
s3://state-bucket/aws/prod/terraform.tfstate
azurerm://state-container/azure/dev/terraform.tfstate
```

**Rules:**
- Never share state across clouds
- Use the native backend for each cloud (S3 for AWS, Azure Blob for Azure)
- Lock state with DynamoDB (AWS) or Azure Blob leases

---

### 5. What does "large-scale Kubernetes" mean and how do you manage it?

**Large-scale = 100+ nodes, 1000+ pods, multiple teams.**

**Challenges and solutions:**
| Challenge | Solution |
|---|---|
| Resource contention | Namespace quotas + LimitRanges |
| Multi-team access | RBAC per team namespace |
| Networking | Network Policies to isolate teams |
| Observability at scale | Per-team Grafana dashboards |
| Cluster upgrades | Canary node groups (upgrade one pool first) |
| Cost | Spot instances for non-critical, right-sizing recommendations |

---

### 6. How do you troubleshoot a failing Pod in Kubernetes?

**Step-by-step debugging:**
```bash
# 1. What's the status?
kubectl get pod <name> -o wide

# 2. WHY is it failing?
kubectl describe pod <name>
# Look at: Events section (bottom) — tells you the real reason

# 3. Check logs
kubectl logs <name>
kubectl logs <name> --previous  # if it crashed and restarted

# 4. Common statuses and fixes:
```

| Status | Meaning | Fix |
|---|---|---|
| Pending | Can't schedule (no node space) | Scale nodes or reduce requests |
| ImagePullBackOff | Can't download image | Check image name, ECR auth, network |
| CrashLoopBackOff | App starts then crashes | Check logs, fix app code |
| OOMKilled | Out of memory | Increase memory limit |
| Init:0/1 | Init container stuck | Check init container logs, missing secrets/configmaps |

---

### 7. Blue-Green deployment in Kubernetes

**Concept:** Two identical environments. Only ONE receives traffic at a time.

```
Blue (current v1) ←── ALB sends traffic here
Green (new v2)    ←── deployed but NOT receiving traffic

After testing Green:
Blue (v1)          ←── traffic REMOVED
Green (v2)     ←── ALB switches traffic here

If Green has issues:
Switch back to Blue instantly (no redeploy needed)
```

**In Kubernetes with Argo Rollouts:**
```yaml
strategy:
  blueGreen:
    activeService: order-service         # Blue (gets traffic)
    previewService: order-service-preview # Green (for testing)
    autoPromotionEnabled: true
    autoPromotionSeconds: 120            # Auto-switch after 2 min
```

---

### 8. How do you ensure Docker image consistency across environments?

**Rules:**
- **Same image everywhere:** dev, staging, prod use the EXACT same Docker image (same SHA digest)
- **Never use `:latest` tag** — it changes and you don't know what version is running
- **Immutable tags:** ECR IMMUTABLE ensures tag can't be overwritten
- **Pin base images:** `FROM python:3.11-slim@sha256:abc123...` (digest pinning)

**Example from my project:**
```
Build: order-service:build-14 → pushed to ECR
Dev: deploys order-service:build-14
Staging: deploys order-service:build-14 (SAME image)
Prod: deploys order-service:build-14 (SAME image)
```

---

### 9. Why SonarQube in CI/CD pipeline — and at what stage?

**Why:** Catches bugs, vulnerabilities, and code smells BEFORE they reach production.

**Where in pipeline:**
```
Build → Test → SonarQube Analysis → Quality Gate → Docker Build → Deploy
                    ↑                      ↑
              Scan the code          If FAILS → pipeline stops
                                     (no deploy of bad code)
```

**Example:**
```groovy
stage('SonarQube Analysis') {
    steps {
        withSonarQubeEnv('SonarQube') {
            sh 'sonar-scanner -Dsonar.projectKey=order-service'
        }
    }
}
stage('Quality Gate') {
    steps {
        waitForQualityGate abortPipeline: true  // STOP if quality fails
    }
}
```

---

### 10. How do you handle Terraform state drift caused by manual changes?

**Detection:**
```bash
terraform plan -refresh-only
# Shows: "~ security_group will be updated (port 8080 was added manually)"
```

**Fix options:**
- Keep manual change → update .tf code to include it → `apply` (no-op)
- Revert manual change → just `apply` → Terraform removes it
- Import the resource if it was created outside Terraform: `terraform import`

**Prevention:**
- Lock AWS console access (read-only for most users)
- All changes through Terraform CI pipeline only
- Scheduled `terraform plan` job that alerts on drift

---

### 11. How do you make Terraform code reusable?

**Use modules:**
```
modules/
├── vpc/          ← reusable VPC module
├── eks/          ← reusable EKS module
└── ec2/          ← reusable EC2 module

environments/
├── dev/   → uses modules with dev.tfvars
└── prod/  → uses same modules with prod.tfvars
```

**Example:**
```hcl
# dev/main.tf
module "vpc" {
  source   = "../modules/vpc"
  vpc_cidr = "10.0.0.0/16"     # dev CIDR
}

# prod/main.tf
module "vpc" {
  source   = "../modules/vpc"
  vpc_cidr = "10.1.0.0/16"     # prod CIDR (different!)
}
```

Same module, different inputs = reusable without duplication.

---

### 12. What monitoring and observability tools have you worked with?

**My stack:**
| Tool | Purpose |
|---|---|
| Prometheus | Metrics collection (pull-based, time-series) |
| Grafana | Visualization (dashboards for everything) |
| Alertmanager | Alert routing (Slack, email, PagerDuty) |
| CloudWatch | AWS-native metrics (billing, ALB, RDS) |
| kube-state-metrics | Kubernetes object metrics (pod status, deployments) |
| Node Exporter | Host-level metrics (CPU, memory, disk) |

**What I monitor:**
- Golden signals: Latency, Errors, Traffic, Saturation
- Kubernetes: pod restarts, scheduling failures, node pressure
- Business: request volume, success rate per service

---

### 13. How does Kubernetes handle traffic spikes?

**HPA (Horizontal Pod Autoscaler):**
```
Normal: 2 pods handling 100 req/sec each → CPU 40%
Spike:  Traffic doubles → CPU hits 80% → HPA adds 2 more pods
After:  Traffic drops → HPA removes extra pods (after 5 min cooldown)
```

**Cluster Autoscaler:**
```
HPA wants 10 pods but only 2 nodes have space for 6
→ 4 pods stay Pending
→ Cluster Autoscaler adds 2 new nodes
→ Pending pods get scheduled
```

---

### 14. How do you perform rollbacks in Kubernetes?

```bash
# Option 1: kubectl rollback (quick)
kubectl rollout undo deployment/order-service -n order-service

# Option 2: Helm rollback (versioned)
helm rollback order-service 2  # Roll back to revision 2

# Option 3: ArgoCD (GitOps)
# Revert the Git commit → ArgoCD auto-syncs to previous version
git revert HEAD
git push

# Option 4: Argo Rollouts (canary)
kubectl argo rollouts abort order-service -n order-service
# Automatically routes all traffic back to stable version
```

---

### 15. How does AWS handle traffic spikes?

**Auto Scaling Group:**
- Predictive scaling: learns traffic pattern, pre-scales before peak
- Target tracking: "Keep CPU at 60%" → adds/removes instances automatically

**ALB:**
- Automatically scales (managed by AWS)
- Cross-zone load balancing distributes evenly

**CloudFront:**
- Caches static content at 400+ edge locations worldwide
- Absorbs 80% of traffic before it reaches your servers

---

### 16. What could cause errors when EC2 instances are running?

| Error | Likely Cause |
|---|---|
| Connection timeout | Security Group blocking port |
| Permission denied | IAM role missing, SSH key wrong |
| Out of memory | Instance type too small, memory leak |
| Disk full | Logs accumulating, Docker images filling disk |
| Application crash | Code bug, missing env variable, wrong config |
| DNS not resolving | Route53 record wrong, TTL cached |

---

### 17. Real-time production issue you identified and troubleshot

**From my project:**

"Users couldn't access Jenkins at `https://jenkins.vosukula.online`. I debugged layer by layer:

1. `nslookup` → DNS resolved to correct ALB IP ✅
2. `kubectl get ingress -n jenkins` → ADDRESS was empty ❌
3. `kubectl describe ingress` → Events showed: `CertificateNotFound: REPLACE_WITH_ACM_CERT_ARN`

Root cause: The ACM certificate ARN placeholder was never replaced with the real ARN. Additionally, the cert was for `vosukula.online` (apex only) — didn't cover `*.vosukula.online` subdomains.

Fix: Requested wildcard cert (`*.vosukula.online`), updated all ingress manifests, re-applied. Also had to wait for Jenkins pod to exit `Init:0/2` because the admin secret was missing.

Three issues stacked: wrong cert ARN + non-wildcard cert + missing secret. Took 2 hours to fully resolve."


---

## SECTION 9: AWS Production Troubleshooting Checklist (10 Scenarios)

---

### 1️⃣ App Crashing due to High Traffic

**Problem:** Single EC2 instance overwhelmed, app becomes unresponsive.

**Fix:**
- Attach an Application Load Balancer (ALB) to distribute traffic
- Create Auto Scaling Group (ASG) with min=2, max=5
- Set target tracking policy: CPU > 70% → scale up

**Tools:** EC2, ALB, ASG, CloudWatch

**Debug:**
```bash
# Check instance CPU
aws cloudwatch get-metric-statistics --namespace AWS/EC2 --metric-name CPUUtilization \
  --dimensions Name=InstanceId,Value=i-xxx --period 300 --statistics Average \
  --start-time 2026-06-29T00:00:00 --end-time 2026-06-29T23:59:59

# Check ALB health
aws elbv2 describe-target-health --target-group-arn <arn>
```

---

### 2️⃣ Slow RDS Database Performance

**Problem:** Users complaining about slow application, bottleneck is the database.

**Fix:**
- Enable Performance Insights → identify slow queries
- Optimize queries: add indexes, rewrite JOINs
- Scale up instance class (db.t3.medium → db.r5.large)
- Deploy Read Replicas for read-heavy workloads
- Consider Aurora (5x faster than standard MySQL)

**Tools:** RDS, Performance Insights, Aurora

**Debug:**
```bash
# Check RDS CPU and connections
aws cloudwatch get-metric-statistics --namespace AWS/RDS --metric-name CPUUtilization \
  --dimensions Name=DBInstanceIdentifier,Value=mydb --period 300 --statistics Average

# Check active connections
aws cloudwatch get-metric-statistics --namespace AWS/RDS --metric-name DatabaseConnections \
  --dimensions Name=DBInstanceIdentifier,Value=mydb --period 60 --statistics Maximum
```

---

### 3️⃣ ASG Not Scaling Out (Despite High CPU)

**Problem:** CPU at 90% but ASG isn't launching new instances.

**Fix:**
- Validate CloudWatch Alarm is in ALARM state (not INSUFFICIENT_DATA)
- Check target tracking thresholds — is the alarm properly configured?
- Check ASG capacity limits — `max_size` might already be reached
- Review AWS Service Quotas (instance limits per region)
- Check if the launch template/AMI still exists

**Tools:** Auto Scaling, CloudWatch

**Debug:**
```bash
# Check ASG activity
aws autoscaling describe-scaling-activities --auto-scaling-group-name myASG

# Check CloudWatch alarm state
aws cloudwatch describe-alarms --alarm-names "HighCPU-Alarm"

# Check service quotas
aws service-quotas get-service-quota --service-code ec2 --quota-code L-1216C47A
```

---

### 4️⃣ S3 Uploads Throwing "Access Denied"

**Problem:** Application can't upload files to S3 bucket.

**Fix (check in this order):**
1. IAM User/Role permissions → does it have `s3:PutObject`?
2. Bucket Policy → is it explicitly denying?
3. Object Ownership settings → is ACL blocking?
4. Service Control Policies (SCPs) at org level → blocking at root?
5. VPC Endpoint policies → restricting S3 access?

**Tools:** S3, IAM, AWS Organizations

**Debug:**
```bash
# Check who you are
aws sts get-caller-identity

# Simulate the permission
aws iam simulate-principal-policy --policy-source-arn arn:aws:iam::123:role/MyRole \
  --action-names s3:PutObject --resource-arns arn:aws:s3:::mybucket/*

# Check bucket policy
aws s3api get-bucket-policy --bucket mybucket
```

---

### 5️⃣ EC2 is Running but Inaccessible from Internet

**Problem:** Instance is running but HTTP/SSH connections timeout.

**Fix (layer by layer):**
1. Security Group → is inbound port 80/443/22 open?
2. Network ACL → is subnet-level firewall allowing traffic?
3. Route Table → does the subnet have `0.0.0.0/0 → igw-xxx` route?
4. Internet Gateway → is it attached to the VPC?
5. Public IP → does the instance have a public/elastic IP?
6. OS firewall → iptables/firewalld blocking inside the instance?

**Tools:** VPC, Security Groups, NACL

**Debug:**
```bash
# Check security group rules
aws ec2 describe-security-groups --group-ids sg-xxx

# Check route table
aws ec2 describe-route-tables --filters Name=association.subnet-id,Values=subnet-xxx

# Check if instance has public IP
aws ec2 describe-instances --instance-ids i-xxx --query "Reservations[0].Instances[0].PublicIpAddress"
```

---

### 6️⃣ Route53 Domain Not Resolving

**Problem:** DNS records configured but domain doesn't resolve.

**Fix:**
- Confirm Hosted Zone NS records match domain registrar's nameservers
- Verify A/Alias/CNAME record values are correct
- Check TTL — old cached records might still be served (wait for TTL expiry)
- Use `dig` or `nslookup` to trace resolution path

**Tools:** Route 53, DNS

**Debug:**
```bash
# Check nameservers
aws route53 get-hosted-zone --id Z06069392VYRLP2HMDXLV --query "DelegationSet.NameServers"

# List records
aws route53 list-resource-record-sets --hosted-zone-id Z06069392VYRLP2HMDXLV

# Test resolution
nslookup jenkins.vosukula.online
dig jenkins.vosukula.online +trace
```

---

### 7️⃣ EBS Volumes Running Out of Space (Disk Full)

**Problem:** Application failing because disk is 100% full.

**Fix:**
- Immediate: clear logs/temp files (`docker system prune -af`, `dnf clean all`)
- Expand: use Elastic Volumes to dynamically increase size (no downtime)
- Prevent: set CloudWatch alarm on disk usage > 80%
- Automate: lifecycle policy to rotate/delete old logs

**Tools:** EBS, CloudWatch

**Debug:**
```bash
# Check disk on instance
df -h
du -sh /var/* | sort -h

# Modify volume (increase size online)
aws ec2 modify-volume --volume-id vol-xxx --size 100

# After modifying, extend filesystem:
sudo growpart /dev/nvme0n1 1
sudo resize2fs /dev/nvme0n1p1  # or xfs_growfs for XFS
```

---

### 8️⃣ Unhealthy Instances Behind an ALB

**Problem:** Health checks failing, ALB removes targets, users get 502/503.

**Fix:**
- Review Target Group health check path — does it return HTTP 200?
- Check the correct port is configured in target group
- Check application logs on the unhealthy instance
- Increase health check timeout/interval for slow-starting apps
- Let ASG replace persistently unhealthy instances

**Tools:** ALB, Target Groups, EC2

**Debug:**
```bash
# Check target health
aws elbv2 describe-target-health --target-group-arn <arn>

# Check health check config
aws elbv2 describe-target-groups --target-group-arns <arn> \
  --query "TargetGroups[0].{Path:HealthCheckPath,Port:HealthCheckPort,Interval:HealthCheckIntervalSeconds}"

# Check instance logs
ssh ec2-user@<ip> "sudo journalctl -u myapp --since '1 hour ago'"
```

---

### 9️⃣ Securing Application Data & Access

**Problem:** Need to harden security for production workloads.

**Fix:**
- Enforce Least Privilege IAM policies (no `*` actions or resources)
- Run instances in private subnets, use NAT Gateway for outbound
- Encrypt data at rest with KMS (EBS, RDS, S3)
- Enable CloudTrail for API audit logging
- Enable GuardDuty for threat detection
- Use Security Hub for compliance checks

**Tools:** IAM, KMS, CloudTrail, GuardDuty

**Debug:**
```bash
# Check for overly permissive policies
aws iam get-policy-version --policy-arn <arn> --version-id v1

# Check if encryption is enabled on S3
aws s3api get-bucket-encryption --bucket mybucket

# Check GuardDuty findings
aws guardduty list-findings --detector-id <id>
```

---

### 🔟 Setting up High Availability & Disaster Recovery (HA/DR)

**Problem:** Single point of failure — one AZ outage takes everything down.

**Fix:**
- Deploy Multi-AZ architecture (RDS Multi-AZ, ASG across AZs)
- Implement S3 Cross-Region Replication (CRR) for data durability
- Set up Route53 Failover routing to DR region
- Automate backups with AWS Backup
- Test DR plan regularly (chaos engineering)

**Tools:** Route 53, S3 CRR, AWS Backup, Multi-AZ RDS

**Architecture:**
```
Primary (us-east-1):
  ALB → ASG (2 AZs) → RDS Multi-AZ
  S3 → CRR → DR region

DR (us-west-2):
  Route53 failover → standby ALB → standby ASG
  RDS Read Replica (promote on failover)
```

**Debug:**
```bash
# Check RDS Multi-AZ status
aws rds describe-db-instances --db-instance-identifier mydb \
  --query "DBInstances[0].MultiAZ"

# Check Route53 health checks
aws route53 list-health-checks

# Check S3 replication status
aws s3api get-bucket-replication --bucket mybucket
```


---

## SECTION 10: My Daily Work Items (What I Do Day-to-Day)

---

### Overview — How to Explain in Interview

> "On a typical day, I manage the full lifecycle of 3 Python microservices running on AWS EKS. I handle CI/CD with Jenkins, GitOps deployments with ArgoCD, infrastructure with Terraform, and monitoring with Prometheus + Grafana. Here's a breakdown of my daily responsibilities:"

---

### 1. Morning Health Check (First 15 min)

**What I do:**
- Check Grafana dashboards for overnight issues — CPU, memory, pod restarts, node health
- Review ArgoCD sync status — are all 3 services Healthy and in-sync?
- Verify Jenkins agent is online and builds from overnight didn't fail
- Quick `kubectl get pods -A | grep -v Running` to spot any problem pods

**Commands I run daily:**
```bash
# Quick cluster health
kubectl get nodes                              # Node status
kubectl get pods -A | grep -v Running          # Only show problems
kubectl get ingress -A                         # Check ALB addresses
kubectl get applications -n argocd             # ArgoCD sync status
```

**What I'm looking for:**
- CrashLoopBackOff → check logs, fix app or config
- Pending pods → node pressure, need to scale
- OutOfSync in ArgoCD → someone changed cluster manually (drift)
- High restart counts → memory leak or misconfigured probes

---

### 2. CI/CD Pipeline Operations (Jenkins)

**Daily tasks:**
- Trigger builds for services that have new code changes
- Monitor pipeline execution — watch for Docker build failures, ECR push errors
- Troubleshoot agent issues (disk full, network disconnects, permission errors)
- Update Jenkinsfile when pipeline improvements are needed

**How my pipeline works:**
```
Developer pushes to GitHub
    ↓
Jenkins (Build with Parameters) → select service + image tag
    ↓
Checkout → Build & Test (parallel) → SonarQube Scan → Docker Build → Push to ECR → Deploy to EKS
    ↓
ArgoCD detects new image tag in Git → auto-syncs to cluster
```

**Common issues I handle:**
| Issue | How I Fix It |
|---|---|
| Agent offline (disk full) | `docker system prune -af` on agent, expand EBS volume |
| ECR push fails | Re-authenticate: `aws ecr get-login-password` |
| Build timeout | Check if agent is overloaded, abort stuck builds |
| "Waiting for executor" | Kill queued builds, increase agent executors |
| Docker build OOM | Increase agent instance type or add swap |

---

### 3. GitOps Deployments (ArgoCD)

**Daily tasks:**
- Monitor ArgoCD dashboard for sync status of all 3 services
- After Jenkins builds, verify ArgoCD picks up the new image tag from Git
- Handle OutOfSync states — investigate if it's expected change or drift
- Manage canary rollouts — promote, pause, or abort using Argo Rollouts

**GitOps flow I manage:**
```
Jenkins builds image → pushes to ECR
    ↓
Jenkins updates image tag in charts/microservice/values-<service>.yaml
    ↓
Jenkins commits and pushes to Git (main branch)
    ↓
ArgoCD polls Git every 3 min → detects change → auto-deploys to EKS
```

**Commands I use:**
```bash
# Check sync status
kubectl get applications -n argocd

# Force a resync if stuck
kubectl -n argocd patch application order-service --type merge -p '{"operation":{"sync":{}}}'

# Monitor canary rollout
kubectl argo rollouts get rollout order-service -n order-service --watch

# Promote canary to full deployment
kubectl argo rollouts promote order-service -n order-service

# Abort bad deployment (instant rollback)
kubectl argo rollouts abort order-service -n order-service
```

---

### 4. Infrastructure Management (Terraform)

**Daily/Weekly tasks:**
- Review and apply Terraform changes for EKS, VPC, IAM, ECR
- Detect drift — `terraform plan -refresh-only` to catch manual console changes
- Handle state lock conflicts when multiple team members apply
- Manage module versions and provider upgrades

**What I manage with Terraform:**
```
VPC (10.0.0.0/16) → 6 subnets (2 public, 2 private, 2 database)
EKS Cluster (expense-dev) → 2 node groups (t3.medium)
ECR Repositories → order-service, payment-service, user-service
IAM Roles → node group, ALB controller, EBS CSI (IRSA)
S3 + DynamoDB → remote state backend with locking
```

**Commands I run:**
```bash
# Check for drift (weekly)
terraform plan -refresh-only -var-file=tfvars/dev/dev.tfvars

# Apply changes after PR review
terraform plan -var-file=tfvars/dev/dev.tfvars
terraform apply -var-file=tfvars/dev/dev.tfvars

# Handle stuck state lock
terraform force-unlock <lock-id>
```

---

### 5. Monitoring & Alerting (Prometheus + Grafana)

**Daily tasks:**
- Review Grafana dashboards — cluster overview, per-service metrics, node health
- Respond to alerts — pod OOMKilled, high restarts, node disk pressure
- Tune alerting thresholds to reduce noise
- Check Prometheus targets — ensure all services are being scraped

**What I monitor (Golden Signals):**
| Signal | What I Check | Alert Threshold |
|---|---|---|
| Latency | p99 response time per service | > 2 seconds for 5 min |
| Errors | HTTP 5xx rate | > 1% for 5 min |
| Traffic | Requests per second | Sudden drop > 50% |
| Saturation | CPU/Memory usage per pod | > 80% for 10 min |

**PromQL queries I use regularly:**
```promql
# Pod restarts in last hour
increase(kube_pod_container_status_restarts_total[1h]) > 3

# CPU usage by namespace
sum(rate(container_cpu_usage_seconds_total[5m])) by (namespace)

# Memory usage percentage
container_memory_usage_bytes / container_spec_memory_limit_bytes * 100

# HTTP error rate
rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) * 100
```

---

### 6. Kubernetes Operations

**Daily tasks:**
- Debug failing pods — read logs, describe pod, check events
- Manage Helm releases — upgrade services, rollback bad deployments
- Handle ingress/ALB issues — DNS records, certificate validation
- Scale services based on load — adjust HPA or manual replica count

**Helm commands I use:**
```bash
# Deploy/upgrade a service
helm upgrade --install order-service ./charts/microservice \
  -f charts/microservice/values-order.yaml \
  --set image.tag=build-25 \
  -n order-service

# Rollback to previous version
helm rollback order-service 1 -n order-service

# Check release history
helm history order-service -n order-service

# Template validation (dry-run)
helm template order-service ./charts/microservice -f charts/microservice/values-order.yaml
```

**Pod debugging flow:**
```bash
# 1. What's wrong?
kubectl get pods -n order-service
# 2. Why?
kubectl describe pod <pod-name> -n order-service
# 3. App logs
kubectl logs <pod-name> -n order-service --previous
# 4. Get inside
kubectl exec -it <pod-name> -n order-service -- /bin/sh
```

---

### 7. Code Quality (SonarQube)

**Tasks:**
- Review scan results after each pipeline build
- Check for new bugs, vulnerabilities, and code smells
- Ensure quality gates pass before deployments proceed
- Work with developers to fix critical/blocker issues

**Access:** `https://sonar.vosukula.online`

---

### 8. Incident Response

**When things break (my process):**
```
1. DETECT  → Grafana alert fires or user reports issue
2. TRIAGE  → Check dashboards → identify affected service → severity
3. MITIGATE → Rollback deployment / scale up / restart pods
4. DEBUG   → Read logs → describe pod → check events → find root cause
5. FIX     → Apply permanent fix, push through pipeline
6. REVIEW  → Write post-mortem, add monitoring for the gap
```

**Quick incident commands:**
```bash
# Immediate rollback
kubectl rollout undo deployment/order-service -n order-service

# Scale up during traffic spike
kubectl scale deployment/order-service --replicas=5 -n order-service

# Check what changed recently
kubectl get events -A --sort-by=.lastTimestamp | head -20

# Check resource pressure
kubectl top nodes
kubectl top pods -n order-service
```

---

### 9. Weekly Tasks

| Task | What I Do |
|---|---|
| Terraform drift check | `terraform plan -refresh-only` on all environments |
| ECR cleanup | Verify lifecycle policies are deleting old images |
| Security review | Check for unused IAM roles, open security groups |
| Cost review | AWS Cost Explorer — spot unexpected spikes |
| Backup validation | Verify EBS snapshots and state file backups |
| Documentation | Update deployment guide with any new learnings |

---

### 10. How to Describe This in a 2-Minute Interview Answer

> "I work as a DevOps Engineer managing a microservices platform on AWS EKS. My daily responsibilities cover the full DevOps lifecycle:
>
> **Infrastructure:** I provision and manage EKS clusters, VPCs, and IAM roles using Terraform with remote state in S3 and DynamoDB locking. I handle drift detection and module upgrades.
>
> **CI/CD:** I maintain Jenkins pipelines that build Docker images, run SonarQube scans, push to ECR, and deploy to Kubernetes. The pipeline supports 3 microservices with parameterized builds.
>
> **GitOps:** ArgoCD watches our Git repo and auto-syncs deployments. When Jenkins updates the image tag in our Helm values and pushes to Git, ArgoCD deploys it — no manual kubectl needed.
>
> **Monitoring:** I use Prometheus + Grafana to monitor the four golden signals. I've set up alerts for pod restarts, OOM kills, and latency spikes. I respond to incidents by rolling back, scaling, or debugging at the pod level.
>
> **Kubernetes:** I manage Helm chart deployments, troubleshoot CrashLoopBackOff and scheduling issues, handle ingress/ALB configuration, and manage canary rollouts with Argo Rollouts.
>
> On a typical day, I start with a health check across Grafana and ArgoCD, support developers through build issues, handle any production incidents, and work on infrastructure improvements like adding network policies or optimizing costs."

---

### Architecture Diagram (Draw on Whiteboard)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          AWS Cloud (us-east-1)                           │
│                                                                         │
│  ┌──────────┐    ┌────────────┐    ┌──────────────────────────────────┐│
│  │ Developer │───→│  GitHub    │───→│  Jenkins (on EKS)               ││
│  └──────────┘    └────────────┘    │  ├── Build Docker Image         ││
│                                     │  ├── SonarQube Scan             ││
│                                     │  ├── Push to ECR                ││
│                                     │  └── Update Git (image tag)     ││
│                                     └──────────────┬─────────────────┘││
│                                                    │ Git push          ││
│                                                    ▼                   ││
│  ┌──────────────────────────────────────────────────────────────────┐ ││
│  │  ArgoCD (watches Git, auto-syncs)                                │ ││
│  └──────────────────────┬───────────────────────────────────────────┘ ││
│                          │ Deploy                                       │
│                          ▼                                              │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  EKS Cluster (expense-dev)                                        │  │
│  │  ├── order-service   (namespace: order-service)                   │  │
│  │  ├── payment-service (namespace: payment-service)                 │  │
│  │  ├── user-service    (namespace: user-service)                    │  │
│  │  ├── monitoring      (Prometheus + Grafana)                       │  │
│  │  └── argo-rollouts   (Canary/Blue-Green)                         │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌─────────┐  ┌─────────┐  ┌────────────┐  ┌───────────┐             │
│  │   ECR   │  │   ALB   │  │  Route53   │  │    ACM    │             │
│  │(images) │  │(ingress)│  │   (DNS)    │  │  (certs)  │             │
│  └─────────┘  └─────────┘  └────────────┘  └───────────┘             │
│                                                                         │
│  Terraform manages: VPC + EKS + ECR + IAM + S3 state backend           │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### Tools & Technologies Summary (for Resume)

| Category | Tools |
|---|---|
| Cloud | AWS (EKS, ECR, VPC, IAM, ALB, Route53, ACM, S3, DynamoDB) |
| IaC | Terraform (modules, remote state, workspaces) |
| Containers | Docker, AWS ECR |
| Orchestration | Kubernetes (EKS), Helm Charts |
| CI/CD | Jenkins (declarative pipelines, shared libraries) |
| GitOps | ArgoCD, Argo Rollouts (canary, blue-green) |
| Monitoring | Prometheus, Grafana, Alertmanager, CloudWatch |
| Code Quality | SonarQube |
| Version Control | Git, GitHub |
| Scripting | Bash, Python (Flask microservices) |
| OS | Linux (RHEL 9, Amazon Linux 2023) |


---

## SECTION 11: AI Agent Implementation Using MCP (Model Context Protocol)

---

### What is MCP? (Simple Explanation for Interview)

> "MCP is an open protocol that lets AI agents call external tools in a standardized way. Think of it as a USB port for AI — any AI agent (Kiro, Claude, custom bots) can plug into any MCP server and use its tools without custom integration code."

**Analogy:**
- Before MCP: Every AI agent needed custom code to talk to kubectl, AWS, GitHub (like every device needing a different charger)
- With MCP: One standard protocol — any agent can call any tool through a common interface (like USB-C for everything)

---

### What I Built — DevOps Monitoring Agent

I built an MCP server that exposes 35+ DevOps tools that any AI agent can call to monitor and diagnose issues in our Kubernetes cluster.

**Architecture:**
```
┌─────────────────┐         ┌────────────────────┐         ┌──────────────────┐
│   AI Agent      │         │   MCP Server       │         │   Infrastructure │
│  (Kiro/Claude)  │──MCP──→│  (mcp_server.py)   │──CLI──→│                  │
│                 │         │                    │         │  ├── Kubernetes  │
│  "Is anything  │←─JSON───│  Tools:            │←─JSON───│  ├── Prometheus  │
│   broken?"     │         │  ├── kubectl ops   │         │  ├── GitHub API  │
│                 │         │  ├── prometheus    │         │  └── AWS CLI     │
└─────────────────┘         │  ├── github        │         └──────────────────┘
                            │  └── aws           │
                            └────────────────────┘
```

**How it works:**
1. I ask the AI agent a question: "Are there any failing pods?"
2. Agent decides which MCP tool to call → `check_failing_pods()`
3. MCP server runs `kubectl get pods -A` under the hood
4. Returns structured output to the agent
5. Agent interprets results and explains in plain English + suggests fixes

---

### Why I Built It (Interview Answer)

> "Instead of manually running kubectl commands and parsing output during incidents, I built an AI-powered monitoring layer. The AI agent can run health checks, detect failures, query Prometheus metrics, check GitHub PRs, and inspect AWS resources — all through natural language. This reduces MTTR because the agent can diagnose issues in seconds that would take me minutes to investigate manually."

---

### Technical Implementation Details

**Framework:** FastMCP (Python library for building MCP servers)

**Tool Categories (35+ tools):**

| Category | Tools | What They Do |
|---|---|---|
| Pod Operations | `list_pods`, `describe_pod`, `get_pod_logs`, `get_pod_events` | Inspect pod state and troubleshoot |
| Failure Detection | `check_failing_pods`, `check_high_restarts`, `check_pending_pods` | Proactive health monitoring |
| Node & Resources | `get_node_status`, `get_node_resource_usage`, `check_high_cpu`, `check_high_memory` | Infrastructure health |
| Deployments | `get_deployments`, `check_rollout_status` | Deployment state tracking |
| Ingress | `get_ingress_status`, `describe_ingress` | Networking/ALB health |
| Prometheus | `query_prometheus`, `check_targets_down`, `check_pod_memory_usage` | Metrics analysis |
| GitHub | `list_repos`, `list_pull_requests`, `create_issue`, `get_workflow_runs` | CI/CD integration |
| AWS | `list_ec2_instances`, `check_ecr_images`, `check_eks_cluster`, `check_alb_health` | Cloud resource monitoring |
| Health Summary | `cluster_health_summary` | Full cluster report in one call |

**Code Example — How a Tool is Defined:**
```python
from fastmcp import FastMCP

mcp = FastMCP("DevOps Platform Monitor")

@mcp.tool
def check_failing_pods() -> str:
    """Detect ALL pods NOT in Running/Completed state across the cluster."""
    result = run_kubectl(["get", "pods", "-A"])
    lines = result.strip().split("\n")
    failing = [line for line in lines[1:] 
               if "Running" not in line and "Completed" not in line]
    if not failing:
        return "✅ All pods are healthy"
    return f"⚠️ {len(failing)} failing pods found:\n" + "\n".join(failing)

@mcp.tool
def query_prometheus(promql: str) -> str:
    """Run a PromQL query against Prometheus."""
    response = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": promql})
    data = response.json()
    # Parse and return formatted results
    ...

if __name__ == "__main__":
    mcp.run()  # Starts the MCP server
```

---

### How the AI Agent Uses It (Real Examples)

**Example 1 — Incident Detection:**
```
Me: "Is anything broken in the cluster?"

Agent calls: cluster_health_summary()
Agent calls: check_failing_pods()

Agent responds: "2 pods are failing:
  - order-service: ImagePullBackOff — image tag 'v99' doesn't exist in ECR
  - sonarqube: CrashLoopBackOff — restarted 5 times
  
  Fix for order-service: The tag 'v99' was never pushed. Run pipeline 
  with correct tag or update values-order.yaml to use 'latest11'."
```

**Example 2 — Performance Investigation:**
```
Me: "Is order-service using too much memory?"

Agent calls: check_pod_memory_usage(namespace="order-service")
Agent calls: query_prometheus("container_memory_usage_bytes{namespace='order-service'}")

Agent responds: "order-service is using 45MB — well within the 256MB limit (18% utilization). 
  No memory pressure. If you're seeing OOMKills, the issue is likely spikes during requests."
```

**Example 3 — Deployment Verification:**
```
Me: "Did the last deployment succeed?"

Agent calls: check_rollout_status(deployment="order-service", namespace="order-service")
Agent calls: get_pod_logs(pod_name="order-service-xyz", namespace="order-service")

Agent responds: "Rollout complete. 2/2 replicas ready. Pod logs show 
  'Listening on port 5000' — service is healthy."
```

---

### Configuration (How Agent Connects to MCP Server)

**In Kiro IDE (`.kiro/settings/mcp.json`):**
```json
{
  "mcpServers": {
    "k8s-monitor": {
      "command": "python",
      "args": ["mcp-server/mcp_server.py"],
      "env": {
        "GITHUB_TOKEN": "ghp_xxx",
        "AWS_REGION": "us-east-1",
        "PROMETHEUS_URL": "http://localhost:9090"
      },
      "disabled": false
    }
  }
}
```

**What happens when agent starts:**
1. Kiro launches `python mcp_server.py` as a subprocess
2. MCP handshake — server advertises its 35+ tools with descriptions
3. Agent now has access to all tools and can call them based on user questions
4. Results come back as JSON/text — agent interprets and presents

---

### Why MCP Over Alternatives (Interview Question)

| Approach | Problem | MCP Advantage |
|---|---|---|
| Custom scripts | Each script needs manual execution | Agent decides WHAT to run based on context |
| ChatOps (Slack bots) | Fixed commands, no intelligence | Agent combines multiple tools intelligently |
| Dashboards (Grafana) | Visual only, need human interpretation | Agent reads metrics AND explains them |
| Runbooks | Sequential steps, no adaptation | Agent adapts investigation path based on findings |
| Direct API integration | Tight coupling, per-agent code | Standard protocol, any agent can use any server |

---

### How to Explain in Interview (2-Minute Version)

> "I built an AI-powered DevOps monitoring agent using the Model Context Protocol. MCP is an open standard that lets AI agents call external tools through a common interface.
>
> My MCP server exposes 35+ tools covering Kubernetes, Prometheus, GitHub, and AWS. Under the hood, it wraps kubectl commands, Prometheus PromQL queries, GitHub API calls, and AWS CLI operations — but exposes them as simple functions with descriptions.
>
> When I ask the AI agent 'Is anything broken?', it calls `cluster_health_summary()` which runs multiple kubectl commands, aggregates the results, and returns a structured report. The agent then interprets this and tells me in plain English what's wrong and how to fix it.
>
> The value is reduced MTTR during incidents. Instead of manually running 10 kubectl commands and parsing output, the agent does it in 2 seconds and gives me a diagnosis. It also enables proactive monitoring — the agent can detect issues like high pod restarts or ImagePullBackOff before users are affected.
>
> I used FastMCP (Python), and it works with Kiro, Claude Desktop, or any MCP-compatible AI. The protocol is transport-agnostic — communicates over stdio or HTTP."

---

### Follow-Up Questions They Might Ask

**Q: What happens if kubectl fails or times out?**
> "Each tool has a 30-second timeout. If kubectl fails, it returns the error message to the agent, and the agent can suggest fixes like 'kubeconfig might be expired — run aws eks update-kubeconfig'."

**Q: How do you handle security? Agent has kubectl access.**
> "The MCP server runs with the same kubeconfig permissions as the user. It only has read access (get, describe, logs) — no write operations like delete or apply. For GitHub and AWS, we use environment variables for tokens with minimal scopes."

**Q: Can the agent take action (fix things) or just report?**
> "Currently read-only for safety. But MCP supports write tools too — we could add `scale_deployment()` or `rollback_deployment()`. The idea is: agent detects + diagnoses, human approves the fix, then agent could execute it."

**Q: How is this different from just using Grafana alerts?**
> "Grafana alerts tell you WHAT is wrong (pod restarted). The AI agent tells you WHY and HOW to fix it. It correlates multiple data points — pod events + logs + metrics + recent deployments — and gives you the root cause in plain English."

**Q: What's the latency? How fast can the agent respond?**
> "Each kubectl call takes 1-3 seconds. The agent typically calls 2-3 tools per question, so total response time is 5-10 seconds. For the full cluster health summary, about 8 seconds to check nodes + pods + restarts + events."

---

### Key Technologies

| Component | Technology | Purpose |
|---|---|---|
| MCP Server | FastMCP (Python) | Expose tools via MCP protocol |
| Kubernetes | kubectl (subprocess) | Cluster operations |
| Metrics | Prometheus REST API | PromQL queries |
| Git | PyGithub library | Repo, PR, commit operations |
| Cloud | AWS CLI (subprocess) + boto3 | EC2, ECR, EKS, ALB, Route53 |
| AI Agents | Kiro, Claude Desktop | Natural language interface |
| Protocol | MCP (stdio transport) | Standard agent-tool communication |


---

## SECTION 12: Tool Connections, Cluster Creation, Secrets Management & Pipeline Communication

---

### Part A: How Different Tools Connect to Each Other

---

#### Q: How does Jenkins connect to your EKS cluster?

**Answer:**

Jenkins agent (EC2) connects to EKS using AWS credentials + kubeconfig:

```
Jenkins Agent (EC2)
    ↓ has AWS credentials (IAM role or access keys)
    ↓ runs: aws eks update-kubeconfig --name expense-dev
    ↓ generates ~/.kube/config with cluster endpoint + token
    ↓ now kubectl works → can deploy to EKS
```

**Two methods we use:**

| Method | How | When |
|---|---|---|
| AWS Credentials Plugin | Jenkins credential store → `aws-credentials` ID → pipeline uses `withCredentials()` | For ECR push, EKS deploy |
| kubeconfig via aws cli | `aws eks update-kubeconfig` in pipeline stage → generates temp kubeconfig | For kubectl/helm commands |

**In our Jenkinsfile:**
```groovy
stage('Deploy to EKS') {
    steps {
        sh 'aws eks update-kubeconfig --region us-east-1 --name expense-dev'
        sh 'kubectl apply -f kubernetes/${SERVICE_NAME}/ -n ${SERVICE_NAME}'
    }
}
```

---

#### Q: How does ArgoCD connect to the EKS cluster?

**Answer:**

ArgoCD runs INSIDE the cluster — so it uses the internal Kubernetes API:

```
ArgoCD (pod in argocd namespace)
    ↓ uses in-cluster ServiceAccount token (auto-mounted)
    ↓ connects to: https://kubernetes.default.svc (internal API server)
    ↓ has ClusterRole permissions (can deploy to any namespace)
```

**In ArgoCD Application manifest:**
```yaml
spec:
  destination:
    server: https://kubernetes.default.svc   # ← Internal cluster API
    namespace: order-service
```

No external credentials needed — it's already inside the cluster with proper RBAC.

---

#### Q: How does ArgoCD connect to GitHub (Git source)?

**Answer:**

ArgoCD polls GitHub to detect changes:

```
ArgoCD → HTTPS → https://github.com/ShivaKrishna44/devops-microservices-platform.git
         (every 3 minutes, checks for new commits on main branch)
```

**For public repos:** No credentials needed — ArgoCD reads via HTTPS.
**For private repos:** Add SSH key or GitHub PAT in ArgoCD settings.

---

#### Q: How does Jenkins connect to ECR (Docker registry)?

**Answer:**

```
Jenkins Agent
    ↓ runs: aws ecr get-login-password --region us-east-1
    ↓ pipes to: docker login --username AWS --password-stdin <ecr-url>
    ↓ now docker push works → pushes image to ECR
```

**Authentication flow:**
1. Jenkins has AWS credentials (stored as Jenkins credential `aws-credentials`)
2. Pipeline calls `aws ecr get-login-password` → gets temporary Docker login token (valid 12 hours)
3. `docker login` with that token → authenticated to ECR
4. `docker push` → image goes to ECR repository

---

#### Q: How does ALB Controller connect to AWS to create Load Balancers?

**Answer:**

Uses **IRSA (IAM Roles for Service Accounts)** — no access keys needed:

```
ALB Controller Pod (kube-system namespace)
    ↓ has ServiceAccount: aws-load-balancer-controller
    ↓ ServiceAccount annotated with IAM role ARN
    ↓ Pod gets temporary AWS credentials via OIDC federation
    ↓ Can call AWS APIs: create ALB, create Target Group, etc.
```

**Trust chain:**
```
EKS OIDC Provider → trusts → ServiceAccount "aws-load-balancer-controller"
    ↓ maps to → IAM Role "expense-dev-alb-controller-role"
    ↓ has → Custom IAM Policy (create/delete ALBs, target groups, etc.)
```

**In Terraform (iam-irsa.tf):**
```hcl
condition {
  test     = "StringEquals"
  variable = "${module.eks.oidc_provider}:sub"
  values   = ["system:serviceaccount:kube-system:aws-load-balancer-controller"]
}
```

---

#### Q: How does Prometheus connect to your applications to scrape metrics?

**Answer:**

Prometheus uses **service discovery** inside the cluster:

```
Prometheus (pod in monitoring namespace)
    ↓ discovers services via Kubernetes API (ServiceMonitor CRDs)
    ↓ scrapes: http://<pod-ip>:5000/metrics every 15 seconds
    ↓ stores time-series data locally
    ↓ Grafana connects to Prometheus API on port 9090
```

**Connection chain:**
- Prometheus → Kubernetes API (discover pods) → Pod IPs (scrape /metrics)
- Grafana → Prometheus (query PromQL) → Display dashboards
- Alertmanager → Prometheus (receives firing alerts) → Sends to Slack/email

---

#### Q: How does Grafana connect to Prometheus?

**Answer:**

Grafana has a datasource configured pointing to Prometheus:

```yaml
# In grafana-values.yaml or auto-configured by kube-prometheus-stack
datasources:
  - name: Prometheus
    type: prometheus
    url: http://monitoring-kube-prometheus-prometheus.monitoring.svc.cluster.local:9090
    access: proxy  # Grafana backend makes the request
```

Both run inside the cluster → communicate via ClusterIP service (internal DNS).

---

#### Q: How does the Jenkins Agent (EC2) connect to Jenkins Controller (EKS)?

**Answer:**

```
Jenkins Agent (EC2 outside cluster)
    ↓ WebSocket connection (HTTPS)
    ↓ connects to: https://jenkins.vosukula.online/
    ↓ authenticates with: secret token (generated when node is created)
    ↓ stays connected → receives build jobs
```

**Command on agent:**
```bash
java -jar agent.jar \
  -url https://jenkins.vosukula.online/ \
  -secret <TOKEN> \
  -name "jenkins-agent" \
  -webSocket \
  -workDir "/home/ec2-user/jenkins-agent"
```

**Key point:** Uses WebSocket (not JNLP) because agent is outside the cluster and needs to traverse the ALB/ingress.

---

#### Q: How does SonarQube integrate with Jenkins?

**Answer:**

```
Jenkins Pipeline
    ↓ Stage: SonarQube Analysis
    ↓ uses: withSonarQubeEnv('SonarQube') → injects SONAR_HOST_URL + token
    ↓ runs: sonar-scanner on the code
    ↓ pushes results to: https://sonar.vosukula.online
    ↓ SonarQube stores analysis → shows in UI
```

**Connection chain:**
1. Jenkins credential store has `sonar-token` (Secret Text)
2. Jenkins System Config has SonarQube server URL
3. Pipeline uses `withSonarQubeEnv()` → auto-injects env vars
4. `sonar-scanner` CLI sends code analysis to SonarQube API

---

### Connection Summary Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                    CONNECTION MAP (How Everything Talks)              │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Developer → GitHub (HTTPS + SSH key or PAT)                         │
│                                                                      │
│  GitHub → Jenkins (Webhook HTTP POST to jenkins.vosukula.online)     │
│                                                                      │
│  Jenkins Agent → Jenkins Controller (WebSocket over HTTPS + token)   │
│                                                                      │
│  Jenkins → ECR (aws ecr get-login-password → docker login)           │
│                                                                      │
│  Jenkins → EKS (aws eks update-kubeconfig → kubectl)                 │
│                                                                      │
│  Jenkins → SonarQube (sonar-token via HTTPS API)                     │
│                                                                      │
│  Jenkins → GitHub (updates image tag, pushes commit via PAT)         │
│                                                                      │
│  ArgoCD → GitHub (polls HTTPS every 3 min, no auth for public repo)  │
│                                                                      │
│  ArgoCD → EKS API (internal: https://kubernetes.default.svc + SA)    │
│                                                                      │
│  ALB Controller → AWS API (IRSA: OIDC → IAM Role → temp creds)      │
│                                                                      │
│  Prometheus → Pods (service discovery → scrape /metrics on pod IPs)  │
│                                                                      │
│  Grafana → Prometheus (internal ClusterIP service, port 9090)        │
│                                                                      │
│  Users → ALB (HTTPS via Route53 DNS → ACM wildcard cert)             │
│                                                                      │
│  MCP Server → kubectl (subprocess call to kubectl binary)            │
│  MCP Server → Prometheus (HTTP REST API on localhost:9090)            │
│  MCP Server → AWS (subprocess call to aws CLI)                       │
│  MCP Server → GitHub (PyGithub library using GITHUB_TOKEN)           │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

### Part B: How Many Ways Can You Create & Connect to a Kubernetes Cluster?

---

#### Q: What are the different ways to create a Kubernetes cluster?

**Answer:**

| Method | What It Is | Use Case | Example |
|---|---|---|---|
| **EKS (AWS Managed)** | AWS manages control plane, you manage nodes | Production on AWS | Our project uses this |
| **kOps** | Provisions cluster on EC2 (self-managed) | Full control needed, cost optimization | Manual EC2 fleet |
| **kubeadm** | Manual bootstrap on any VMs | On-prem, custom setup | Data center Kubernetes |
| **Minikube** | Single-node cluster on laptop | Local development | Testing on your machine |
| **Kind (K8s in Docker)** | Cluster running inside Docker containers | CI testing, fast spinup | GitHub Actions tests |
| **k3s** | Lightweight K8s (single binary) | Edge, IoT, resource-constrained | Raspberry Pi, small VMs |
| **EKS Anywhere** | EKS on your own hardware | Hybrid cloud | On-prem with AWS tooling |
| **GKE (Google)** | Google's managed K8s | Multi-cloud, Google-centric | Alternative to EKS |
| **AKS (Azure)** | Azure's managed K8s | Azure environment | Microsoft shops |
| **Rancher** | Multi-cluster management platform | Managing many clusters | Enterprise K8s fleet |
| **Terraform + EKS module** | IaC-provisioned EKS | Reproducible, automated | Our project |
| **eksctl** | CLI tool for EKS | Quick setup, less control | Prototyping |

**In my project, I use Terraform + EKS module:**
```hcl
module "eks" {
  source          = "terraform-aws-modules/eks/aws"
  version         = "~> 20.0"
  cluster_name    = "expense-dev"
  cluster_version = "1.33"
  vpc_id          = module.vpc.vpc_id
  subnet_ids      = module.vpc.private_subnet_ids
}
```

---

#### Q: What are the different ways to connect to a Kubernetes cluster?

**Answer:**

| Method | How | Use Case |
|---|---|---|
| **aws eks update-kubeconfig** | Generates kubeconfig with AWS IAM auth | EKS clusters (our approach) |
| **kubeconfig file** | Direct certificate-based auth in `~/.kube/config` | Any cluster with certs |
| **Service Account token** | Pod mounts token at `/var/run/secrets/kubernetes.io/serviceaccount/token` | Apps inside cluster (ArgoCD, Prometheus) |
| **OIDC/SSO** | Dex, Keycloak → federated identity | Enterprise multi-team access |
| **kubectl proxy** | Local proxy to API server | Quick debugging |
| **Port-forward** | Forward local port to cluster service | Access internal services |
| **Exec into pod** | `kubectl exec -it pod -- /bin/sh` | Debug from inside |
| **Lens/K9s** | GUI/TUI tools using kubeconfig | Day-to-day operations |
| **CI/CD (Jenkins)** | `aws eks update-kubeconfig` in pipeline | Automated deployments |
| **IRSA (Service Account → IAM)** | OIDC federation, no credentials in pod | AWS services from pods |

**Example — 3 different contexts connecting to same cluster:**
```bash
# Human (from laptop):
aws eks update-kubeconfig --name expense-dev --region us-east-1
kubectl get pods

# Jenkins (from EC2 agent):
aws eks update-kubeconfig --name expense-dev    # In pipeline stage
kubectl apply -f manifests/

# ArgoCD (from inside cluster):
# No config needed — uses in-cluster ServiceAccount automatically
# Connects to: https://kubernetes.default.svc
```

---

#### Q: What is kubeconfig and how does authentication work?

**Answer:**

kubeconfig has 3 parts:
```yaml
# ~/.kube/config
clusters:
  - cluster:
      server: https://ABC123.gr7.us-east-1.eks.amazonaws.com  # WHERE to connect
      certificate-authority-data: <base64-cert>                 # HOW to verify server
    name: expense-dev

users:
  - user:
      exec:
        command: aws                                            # WHO you are
        args: ["eks", "get-token", "--cluster-name", "expense-dev"]
    name: arn:aws:iam::589389425618:user/admin

contexts:
  - context:
      cluster: expense-dev                                     # WHICH cluster + user
      user: arn:aws:iam::589389425618:user/admin
    name: expense-dev
```

**Authentication flow for EKS:**
```
kubectl get pods
    ↓
kubeconfig says: run "aws eks get-token"
    ↓
AWS returns: temporary bearer token (valid 15 min)
    ↓
kubectl sends: token to EKS API server
    ↓
EKS validates: token with IAM → maps to Kubernetes RBAC
    ↓
Returns: pod list (if authorized)
```

---

### Part C: How Many Ways Can You Provide Secure Data (Secrets Management)?

---

#### Q: What are the different ways to manage secrets in Kubernetes?

**Answer:**

| Method | Security Level | How It Works | Use Case |
|---|---|---|---|
| **Kubernetes Secrets** | Basic (base64 encoded, NOT encrypted) | `kubectl create secret` → mounted as env/volume | Simple apps, dev environments |
| **Helm values + existingSecret** | Medium | Reference pre-created K8s secret in Helm values | Jenkins admin password (our approach) |
| **AWS Secrets Manager** | High | Store in AWS, fetch at runtime | Production secrets |
| **External Secrets Operator** | High | Syncs AWS Secrets Manager → K8s Secrets automatically | Best of both worlds |
| **HashiCorp Vault** | Very High | Centralized secret store with rotation, audit | Enterprise, multi-cloud |
| **Sealed Secrets** | High | Encrypt secrets in Git, decrypt in cluster | GitOps-safe secrets |
| **SOPS (Mozilla)** | High | Encrypt files with AWS KMS, decrypt at deploy | Terraform secrets, Helm values |
| **AWS SSM Parameter Store** | Medium-High | Key-value store in AWS, IAM-controlled access | Config + secrets |
| **IRSA (IAM Roles for Service Accounts)** | High | No secrets at all — pod gets IAM role via OIDC | AWS service access (our ALB controller) |
| **Jenkins Credentials Store** | Medium | Encrypted in Jenkins master, injected into pipeline | CI/CD pipeline secrets |
| **Environment Variables in pod spec** | Low | Hardcoded in deployment YAML | Never for production |

---

#### Q: How do you handle secrets in YOUR project?

**Answer:**

We use multiple methods depending on the context:

```
┌─────────────────────────────────────────────────────────────────┐
│                   SECRETS IN OUR PROJECT                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Jenkins Admin Password:                                          │
│    → Kubernetes Secret (kubectl create secret)                    │
│    → Referenced in Helm values: existingSecret: jenkins-admin-secret│
│                                                                   │
│  Grafana Admin Password:                                          │
│    → Kubernetes Secret (grafana-admin-secret)                     │
│    → Referenced in Helm values                                    │
│                                                                   │
│  AWS Credentials for Jenkins Pipeline:                            │
│    → Jenkins Credentials Store (ID: aws-credentials)              │
│    → Injected via withCredentials() in pipeline                   │
│                                                                   │
│  SonarQube Token:                                                 │
│    → Jenkins Credentials (Secret Text, ID: sonar-token)           │
│    → Injected via withSonarQubeEnv()                              │
│                                                                   │
│  ALB Controller AWS Access:                                       │
│    → IRSA (no secrets!) — OIDC federation → IAM Role              │
│    → Pod auto-gets temp credentials via service account           │
│                                                                   │
│  EBS CSI Driver AWS Access:                                       │
│    → IRSA (same pattern as ALB controller)                        │
│                                                                   │
│  ArgoCD Admin Password:                                           │
│    → Auto-generated Kubernetes Secret (argocd-initial-admin-secret)│
│    → Retrieved via: kubectl get secret ... | base64 -d            │
│                                                                   │
│  GitHub Token (for MCP/ArgoCD):                                   │
│    → Environment variable on the machine running MCP server       │
│    → Or ArgoCD repo credential secret                             │
│                                                                   │
│  ECR Authentication:                                              │
│    → Temporary token (aws ecr get-login-password, valid 12h)      │
│    → No permanent credentials stored                              │
│                                                                   │
│  Terraform State:                                                 │
│    → S3 bucket with server-side encryption (SSE-S3)               │
│    → Access controlled by IAM policies                            │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

#### Q: What is IRSA and why is it better than access keys?

**Answer:**

**Traditional (bad):**
```
Create IAM user → generate access keys → store in K8s secret → mount in pod
Problems: keys never expire, shared across pods, hard to rotate, leaked = full access
```

**IRSA (good):**
```
Create IAM role → annotate K8s ServiceAccount → pod auto-gets temporary credentials
Benefits: no stored keys, credentials rotate every 15 min, pod-specific, auto-expires
```

**How IRSA works in our project (ALB Controller):**
```
1. Terraform creates IAM role with trust policy
2. Trust policy says: "Only pod with ServiceAccount 'aws-load-balancer-controller' in namespace 'kube-system' can assume this role"
3. EKS OIDC provider verifies the pod identity
4. Pod gets temporary AWS credentials (auto-injected by EKS)
5. Pod can call AWS APIs (create ALB, etc.) — no access keys anywhere
```

---

### Part D: Communication Between Tools/Stages During Pipeline

---

#### Q: Explain how communication happens between all tools during a CI/CD pipeline run.

**Answer — Complete Flow with Protocols:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FULL PIPELINE COMMUNICATION FLOW                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  TRIGGER:                                                                    │
│  Developer → git push → GitHub (SSH/HTTPS)                                   │
│  GitHub → Webhook POST → jenkins.vosukula.online (HTTPS)                     │
│  Jenkins Controller → assigns job → Jenkins Agent (WebSocket)                │
│                                                                              │
│  STAGE 1 - CHECKOUT:                                                         │
│  Jenkins Agent → git clone → GitHub (HTTPS, public repo)                     │
│  Protocol: HTTPS (port 443)                                                  │
│  Auth: None (public repo) or GitHub PAT (private repo)                       │
│                                                                              │
│  STAGE 2 - BUILD & TEST:                                                     │
│  Jenkins Agent → runs locally on agent disk                                  │
│  No external communication — pure compute                                    │
│                                                                              │
│  STAGE 3 - SONARQUBE SCAN:                                                   │
│  Jenkins Agent → sonar-scanner CLI → SonarQube API (HTTPS)                   │
│  Protocol: HTTPS (port 443) to sonar.vosukula.online                         │
│  Auth: SONAR_TOKEN (injected by withSonarQubeEnv from Jenkins credentials)   │
│  Data: Source code metrics uploaded to SonarQube                             │
│                                                                              │
│  STAGE 4 - DOCKER BUILD:                                                     │
│  Jenkins Agent → Docker daemon (local Unix socket or TCP)                    │
│  Docker → pulls base image from Docker Hub (HTTPS, port 443)                 │
│  Result: Local Docker image built on agent                                   │
│                                                                              │
│  STAGE 5 - ECR LOGIN & PUSH:                                                │
│  Jenkins Agent → AWS STS (HTTPS) → validates credentials                     │
│  Jenkins Agent → ECR API (HTTPS) → gets temp Docker login token              │
│  Jenkins Agent → docker push → ECR registry (HTTPS, port 443)                │
│  Protocol: HTTPS                                                             │
│  Auth: AWS access key → STS → temporary ECR token (12h expiry)               │
│                                                                              │
│  STAGE 6 - DEPLOY TO EKS:                                                    │
│  Jenkins Agent → AWS EKS API (HTTPS) → gets kubeconfig + token               │
│  Jenkins Agent → kubectl → EKS API server (HTTPS, port 443)                  │
│  Protocol: HTTPS with bearer token                                           │
│  Auth: AWS IAM → mapped to K8s RBAC (via aws-auth ConfigMap or access entry) │
│                                                                              │
│  STAGE 7 - GITOPS UPDATE (alternative to direct deploy):                     │
│  Jenkins Agent → git commit (update image tag in values-order.yaml)           │
│  Jenkins Agent → git push → GitHub (HTTPS with PAT)                          │
│  ArgoCD → polls GitHub (HTTPS, every 3 min)                                  │
│  ArgoCD → detects change → applies to EKS API (internal HTTPS)               │
│  Protocol: HTTPS for Git, internal HTTPS for K8s API                         │
│  Auth: GitHub PAT for push, ServiceAccount for K8s                           │
│                                                                              │
│  POST-DEPLOY - VERIFICATION:                                                 │
│  ALB Controller → watches Ingress resources (K8s API)                        │
│  ALB Controller → AWS API (create/update ALB) via IRSA                       │
│  Route53 → DNS resolution → ALB → Pod                                        │
│  User → HTTPS → ALB → Pod (port 5000)                                       │
│                                                                              │
│  MONITORING:                                                                 │
│  Prometheus → scrapes pods (HTTP on pod IPs, port-specific)                  │
│  Grafana → queries Prometheus (HTTP internal, port 9090)                     │
│  Alertmanager → receives from Prometheus → sends to Slack (HTTPS webhook)    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

#### Q: What protocols are used at each stage?

**Answer:**

| Communication | Protocol | Port | Auth Method |
|---|---|---|---|
| Developer → GitHub | SSH or HTTPS | 22 / 443 | SSH key or PAT |
| GitHub → Jenkins (webhook) | HTTPS | 443 | Webhook secret |
| Jenkins Controller → Agent | WebSocket (HTTPS) | 443 | Secret token |
| Jenkins → GitHub (clone) | HTTPS | 443 | None (public) or PAT |
| Jenkins → SonarQube | HTTPS | 443 | API token |
| Jenkins → ECR | HTTPS | 443 | AWS temp token (12h) |
| Jenkins → EKS API | HTTPS | 443 | IAM → Bearer token (15 min) |
| ArgoCD → GitHub | HTTPS | 443 | None or deploy key |
| ArgoCD → K8s API | HTTPS (internal) | 443 | ServiceAccount token |
| ALB Controller → AWS | HTTPS | 443 | IRSA (temp creds, 15 min) |
| Prometheus → Pods | HTTP | varies (5000, 9090, etc.) | None (internal) |
| Grafana → Prometheus | HTTP (internal) | 9090 | None (ClusterIP) |
| User → Application | HTTPS | 443 | ACM cert on ALB |

---

#### Q: How do stages pass data between each other in the pipeline?

**Answer:**

| What's Passed | From → To | How |
|---|---|---|
| Source code | GitHub → Agent workspace | `git clone` downloads to local disk |
| Build artifacts | Build stage → Docker stage | Shared workspace directory (same agent) |
| Docker image | Docker build → ECR | `docker push` (uploads layers) |
| Image tag | ECR push → Deploy stage | Environment variable `${FULL_IMAGE_NAME}` in Jenkinsfile |
| kubeconfig | AWS → kubectl | Written to `~/.kube/config` by `aws eks update-kubeconfig` |
| SonarQube results | Agent → SonarQube server | HTTP upload during scan |
| Pipeline status | Jenkins → Developer | Console output, email, Slack notification |
| Image tag for GitOps | Jenkins → Git → ArgoCD | Git commit updating values YAML file |

**Key insight:** Within a single pipeline run, data passes through the shared workspace (disk) and environment variables. Between tools, data passes via APIs (HTTPS) and Git.

---

#### Q: What happens if one connection fails?

**Answer:**

| Failure Point | Impact | How to Detect | Fix |
|---|---|---|---|
| Agent → Controller disconnects | Builds stop, queue backs up | Jenkins UI: node shows offline | Reconnect agent, check network |
| ECR login fails | Can't push image, pipeline fails | Stage error: "no credentials" | Rotate AWS keys, check IAM |
| EKS kubeconfig fails | Can't deploy | "Unable to connect to server" | Check IAM permissions, cluster status |
| ArgoCD → GitHub fails | No auto-sync, deployments stall | ArgoCD UI: "ComparisonError" | Check repo URL, credentials |
| Prometheus scrape fails | Missing metrics, stale dashboards | Targets page shows "down" | Check network policy, pod health |
| SonarQube unreachable | Quality gate skipped or fails | Pipeline stage timeout | Check SonarQube pod, ingress |

---

#### Q: How to explain all of this in an interview (2-minute summary)?

**Answer:**

> "In my CI/CD pipeline, communication between tools happens primarily over HTTPS with different authentication methods at each stage:
>
> **Trigger:** A GitHub webhook hits Jenkins over HTTPS when code is pushed.
>
> **Build:** Jenkins Controller assigns the job to an EC2 agent connected via WebSocket. The agent clones code from GitHub, builds a Docker image, then authenticates to ECR using temporary AWS tokens and pushes the image.
>
> **Deploy (GitOps):** Jenkins updates the image tag in a Helm values file and pushes to Git. ArgoCD, running inside the EKS cluster, polls GitHub every 3 minutes. When it detects the change, it syncs the new version using the internal Kubernetes API with its ServiceAccount token.
>
> **Networking:** The ALB Controller uses IRSA — it has no stored credentials. Instead, it gets temporary AWS credentials through OIDC federation every 15 minutes. It watches Ingress resources and creates/updates ALBs automatically.
>
> **Monitoring:** Prometheus discovers and scrapes pods internally using Kubernetes service discovery. Grafana queries Prometheus via ClusterIP. All internal communication is HTTP within the cluster; all external-facing communication is HTTPS with ACM certificates on the ALB.
>
> **Secrets:** We use Kubernetes Secrets for application passwords, Jenkins Credentials Store for pipeline secrets, IRSA for AWS access (no keys stored), and temporary tokens wherever possible to minimize exposure."


**1. Terraform Layer Debugging****

-Check Terraform State   
terraform state list

-Check Resource Details
terraform state show aws_iam_role.ebs_csi

-Validate Syntax
terraform validate

-Check Formatting
terraform fmt -recursive

-Preview Changes
terraform plan

-Refresh State
terraform refresh

**Compare AWS vs State**

-terraform state list
aws eks list-access-entries --cluster-name expense-dev

-Debug Failed Resource
terraform apply -target=aws_eks_addon.ebs_csi

**2. AWS EKS Cluster Debugging**
   
-Verify Cluster Exists
aws eks list-clusters

-Cluster Health
aws eks describe-cluster --name expense-dev

-Update Kubeconfig
aws eks update-kubeconfig --region us-east-1 --name expense-dev

-Verify Connectivity
kubectl cluster-info

-Verify Nodes
kubectl get nodes -o wide


**3. EKS Access Entry Debugging**

-List Access Entries
aws eks list-access-entries --cluster-name expense-dev

-List Policies
aws eks list-associated-access-policies --cluster-name expense-dev --principal-arn arn:aws:iam::589389425618:root

-Check Terraform State
terraform state list | grep access

**4. Node Group Debugging****
-Check Node Group
aws eks list-nodegroups --cluster-name expense-dev

-Node Group Details
aws eks describe-nodegroup --cluster-name expense-dev --nodegroup-name dev

-Check EC2
aws ec2 describe-instances

**5. IAM Debugging**

-Check Role
aws iam get-role --role-name expense-dev-ebs-csi-role

-Attached Policies
aws iam list-attached-role-policies --role-name expense-dev-ebs-csi-role

-Check OIDC Provider 
aws iam list-open-id-connect-providers

**6. IRSA Debugging**

-Check Service Account
kubectl get sa -n kube-system

-Check Annotation
kubectl get sa ebs-csi-controller-sa -n kube-system -o yaml

-Expected:
eks.amazonaws.com/role-arn:

-Verify ALB Controller Role
kubectl get sa aws-load-balancer-controller -n kube-system -o yaml

**7. EBS CSI Driver Debugging**

-This was one of your biggest issues.

-Pods
kubectl get pods -n kube-system | grep ebs

Expected:
Running Logs :- kubectl logs -n kube-system deploy/ebs-csi-controller

or
kubectl logs -n kube-system <ebs-csi-pod-name>

-Describe -  kubectl describe pod -n kube-system <ebs-csi-pod-name>

Common Error: UnauthorizedOperation

Means:  IAM/IRSA issue

**8. PVC Debugging**

-Check PVC
kubectl get pvc -A

-Describe PVC
kubectl describe pvc -n jenkins

Expected: Bound
Common Error: Pending

Cause: StorageClass - EBS CSI

**9. StorageClass Debugging**
 
-List Storage Classes
kubectl get storageclass

Expected: gp2  gp3

-Default StorageClass
kubectl get sc

Look for: (default)

**10. Jenkins Debugging**

-Pod Status
kubectl get pods -n jenkins

Logs - kubectl logs -n jenkins jenkins-0

-Describe Pod
kubectl describe pod -n jenkins jenkins-0

- PVC
kubectl get pvc -n jenkins

**11. Jenkins Credentials Debugging**

**Inside Jenkins:**

Manage Jenkins
→ Credentials

Verify: GitHub ,AWS ,SSH Agent

**12. Jenkins Agent Debugging**

Check Nodes -> Manage Jenkins
→ Nodes

Expected: Online 
Agent Logs
Node
→ Log

Common Error:
Waiting for next available executor

Means:

Agent offline
Label mismatch
No executor
1.  Docker Debugging
Images
docker images

or

podman images
Build
docker build -t test .
Running Containers
docker ps -a

14. ECR Debugging
Repositories
aws ecr describe-repositories
Images
aws ecr describe-images \
--repository-name order-service
Login Test
aws ecr get-login-password \
--region us-east-1

15. Kubernetes Deployment Debugging
Deployments
kubectl get deploy -A
Pods
kubectl get pods -A
Describe
kubectl describe deploy order-service
Rollout
kubectl rollout status deployment/order-service
Restart
kubectl rollout restart deployment/order-service

16. Service Debugging
Services
kubectl get svc -A
Describe
kubectl describe svc jenkins -n jenkins

Common Error:
EXTERNAL-IP Pending

Cause:
ALB Controller
IAM
Subnet Tagging
17. ALB Controller Debugging
Pods
kubectl get pods \
-n kube-system \
| grep load-balancer
Logs
kubectl logs \
-n kube-system \
deployment/aws-load-balancer-controller

Common Error:

AccessDenied

Means:
IAM Policy Missing
18. Ingress Debugging
19. 
List - kubectl get ingress -A
Describe - kubectl describe ingress -n jenkins jenkins-ingress

Common Errors:

No certificate found
No ALB created
Target group unhealthy
19. Route53 Debugging
Hosted Zones
aws route53 list-hosted-zones
Records
aws route53 list-resource-record-sets \
--hosted-zone-id <zone-id>
DNS Lookup
nslookup jenkins.vosukula.online

or

dig jenkins.vosukula.online
20. End-to-End Verification

When everything is working:

terraform plan
kubectl get nodes
kubectl get pods -A
kubectl get pvc -A
kubectl get ingress -A
kubectl get svc -A
aws ecr describe-repositories
aws eks list-access-entries \
--cluster-name expense-dev

These 8 commands alone will tell you the health of almost the entire platform in under 2 minutes.

For your project, the Top 5 commands that saved us most often were:

kubectl describe pod
kubectl logs
kubectl describe svc
terraform state list
aws iam list-attached-role-policies

If you master interpreting the output of those five, you'll solve most EKS/Jenkins/Terraform issues without external help.



---

## SECTION 14: Jenkins Shared Libraries — When & Why to Use Them

---

### What Are Shared Libraries?

> "Shared Libraries are reusable Groovy code stored in a separate Git repo that multiple Jenkinsfiles can import and call. Instead of copying the same pipeline logic into 50 Jenkinsfiles, you write it once in the shared library and all pipelines reference it."

**Analogy:** Instead of every developer writing their own Docker build script, you create ONE standard function that everyone calls.

---

### The Problem (Why Shared Libraries Exist)

**Without shared libraries (our current project — 3 services):**

```groovy
// order-service/Jenkinsfile
stage('Docker Build & Push') {
    sh 'aws ecr get-login-password | docker login ...'
    sh 'docker build -t order-service:${TAG} .'
    sh 'docker push ${ECR}/order-service:${TAG}'
}

// payment-service/Jenkinsfile  (SAME code copy-pasted!)
stage('Docker Build & Push') {
    sh 'aws ecr get-login-password | docker login ...'
    sh 'docker build -t payment-service:${TAG} .'
    sh 'docker push ${ECR}/payment-service:${TAG}'
}

// user-service/Jenkinsfile  (SAME code copy-pasted AGAIN!)
stage('Docker Build & Push') {
    sh 'aws ecr get-login-password | docker login ...'
    sh 'docker build -t user-service:${TAG} .'
    sh 'docker push ${ECR}/user-service:${TAG}'
}
```

**Problems:**
- Same code in 3 places (now imagine 50 microservices!)
- Bug fix needed? Must update ALL 50 Jenkinsfiles
- Different teams write inconsistent pipelines
- No quality control over pipeline logic

---

### The Solution — Shared Library

**Shared library repo structure:**
```
jenkins-shared-library/        (separate Git repo)
├── vars/
│   ├── dockerBuildPush.groovy     ← called as dockerBuildPush() in any pipeline
│   ├── deployToEKS.groovy         ← called as deployToEKS()
│   ├── sonarScan.groovy           ← called as sonarScan()
│   └── notifySlack.groovy         ← called as notifySlack()
└── src/
    └── com/company/Utils.groovy   ← helper classes (optional)
```

**vars/dockerBuildPush.groovy:**
```groovy
def call(String serviceName, String tag, String registry) {
    sh """
        aws ecr get-login-password --region us-east-1 | \
          docker login --username AWS --password-stdin ${registry}
        docker build -t ${serviceName}:${tag} .
        docker tag ${serviceName}:${tag} ${registry}/${serviceName}:${tag}
        docker push ${registry}/${serviceName}:${tag}
        docker rmi ${serviceName}:${tag} || true
    """
}
```

**vars/deployToEKS.groovy:**
```groovy
def call(String serviceName, String tag, String cluster, String namespace) {
    sh """
        aws eks update-kubeconfig --name ${cluster} --region us-east-1
        kubectl set image deployment/${serviceName} \
          ${serviceName}=${env.ECR_REGISTRY}/${serviceName}:${tag} \
          -n ${namespace}
        kubectl rollout status deployment/${serviceName} -n ${namespace} --timeout=300s
    """
}
```

**vars/sonarScan.groovy:**
```groovy
def call(String projectKey) {
    withSonarQubeEnv('SonarQube') {
        sh "sonar-scanner -Dsonar.projectKey=${projectKey}"
    }
    timeout(time: 5, unit: 'MINUTES') {
        waitForQualityGate abortPipeline: true
    }
}
```

---

### Now Each Jenkinsfile Becomes Simple

**After shared library — ANY service's Jenkinsfile:**
```groovy
@Library('my-shared-library') _

pipeline {
    agent { label 'AGENT' }
    
    parameters {
        choice(name: 'SERVICE_NAME', choices: ['order-service', 'payment-service', 'user-service'])
        string(name: 'IMAGE_TAG', defaultValue: 'latest')
    }
    
    stages {
        stage('Build & Push') {
            steps {
                dir("app/${params.SERVICE_NAME}") {
                    dockerBuildPush(params.SERVICE_NAME, params.IMAGE_TAG, env.ECR_REGISTRY)
                }
            }
        }
        
        stage('SonarQube') {
            steps {
                dir("app/${params.SERVICE_NAME}") {
                    sonarScan(params.SERVICE_NAME)
                }
            }
        }
        
        stage('Deploy') {
            steps {
                deployToEKS(params.SERVICE_NAME, params.IMAGE_TAG, 'expense-dev', params.SERVICE_NAME)
            }
        }
        
        stage('Notify') {
            steps {
                notifySlack("✅ ${params.SERVICE_NAME}:${params.IMAGE_TAG} deployed")
            }
        }
    }
}
```

**From 150 lines of repeated code → 30 lines calling shared functions.**

---

### Scenarios When You NEED Shared Libraries

| Scenario | Why Shared Library Helps |
|---|---|
| **10+ microservices** with same build pattern | Write once, import everywhere |
| **Multiple teams** building pipelines | Enforce standards, prevent bad practices |
| **Security requirements** (ECR login, credentials) | Centralize secret handling logic |
| **Pipeline bug fix** needed across all services | Fix in ONE place → all pipelines get the fix |
| **New team members** joining | They just call `dockerBuildPush()` — don't need to understand internals |
| **Compliance/audit** requirements | Standard stages (SonarQube, security scan) can't be skipped |
| **Different languages** same pipeline | `buildJava()`, `buildPython()`, `buildNode()` — each in shared lib |
| **Notification standardization** | Every pipeline notifies Slack the same way |
| **Environment promotion** | `deployToEnv('dev')`, `deployToEnv('prod')` — same logic, different targets |

---

### Real-World Example: Company with 50 Microservices

```
Company has:
  - 50 microservices (Java, Python, Node.js)
  - 5 dev teams
  - Environments: dev, staging, prod
  - Each service needs: build → test → scan → Docker → push → deploy → notify

Without shared library: 50 × 150 lines = 7,500 lines of duplicated pipeline code
With shared library:   50 × 30 lines = 1,500 lines + 200 lines in shared lib

Maintenance:
  - ECR login changes? Update 1 file vs 50 files
  - Add security scan stage? Update 1 file vs 50 files
  - Fix SonarQube timeout? Update 1 file vs 50 files
```

---

### How to Configure in Jenkins

**Step 1: Create shared library Git repo** (e.g., `github.com/company/jenkins-shared-library`)

**Step 2: Configure in Jenkins UI:**
- Manage Jenkins → System → Global Pipeline Libraries
- Name: `my-shared-library`
- Default version: `main`
- Source: Git → URL of the shared library repo

**Step 3: Use in any Jenkinsfile:**
```groovy
@Library('my-shared-library') _    // Import the library

pipeline {
    stages {
        stage('Build') {
            steps {
                dockerBuildPush('order-service', '1.0', env.ECR_REGISTRY)
            }
        }
    }
}
```

---

### How to Explain in Interview

> "In our project with 3 microservices, we use a single parameterized Jenkinsfile. But in my previous experience with larger teams (50+ services), we used Jenkins Shared Libraries.
>
> The shared library is a separate Git repo containing reusable Groovy functions — `dockerBuildPush()`, `deployToEKS()`, `sonarScan()`, `notifySlack()`. Any team's Jenkinsfile just imports the library and calls these functions with service-specific parameters.
>
> This solves three problems: code duplication (write once, use 50 times), consistency (all teams follow the same build standards), and maintainability (fix a bug in one place, all pipelines get the fix instantly).
>
> For example, when we changed our ECR authentication method, I updated one file in the shared library — and all 50 microservice pipelines picked up the change on their next build. Without the library, that would have been 50 PRs across 50 repos."

---

### When NOT to Use Shared Libraries

| Situation | Why |
|---|---|
| 1-3 services only | Overhead not worth it — just use parameterized Jenkinsfile (like our project) |
| Each service has completely different build | No common patterns to extract |
| Team is very small (1-2 people) | One person can manage a few Jenkinsfiles manually |
| Using GitHub Actions/GitLab CI | They have their own reuse mechanism (composite actions, CI templates) |

**Our project's approach:** We use ONE parameterized Jenkinsfile with `SERVICE_NAME` parameter — this works well for 3 similar services. Shared libraries would make sense if we grew to 10+ services or multiple teams.
