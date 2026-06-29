# DevOps Interview Preparation — Simplified with Examples

---

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
