# DevOps Microservices Platform — Complete Deployment Guide

A step-by-step guide to deploy the full platform from scratch.

---

## 📚 Documentation Map (Start Here)

| # | Document | Covers | When to Read |
|---|---|---|---|
| 1 | **DEPLOYMENT-GUIDE.md** (this file) | Steps 1–8: Infrastructure → Jenkins → ArgoCD → Monitoring → Agent → Pipeline | First — sets up the entire platform |
| 2 | **PHASES-IMPLEMENTATION.md** | Phases 1–5: SonarQube → Helm Charts → ArgoCD GitOps → Monitoring → Canary/Blue-Green | After base platform is running — adds advanced capabilities |
| 3 | **TROUBLESHOOTING.md** | Every error encountered and how it was fixed | Reference when something breaks |

**Reading order:** Start with this file (DEPLOYMENT-GUIDE), follow Steps 1–8 to get the platform running. Then move to PHASES-IMPLEMENTATION for advanced features.

---

## Project Overview

| Component | Tool | URL |
|---|---|---|
| Infrastructure | Terraform + AWS EKS | — |
| CI/CD | Jenkins (Helm on EKS) | https://jenkins.vosukula.online |
| GitOps | ArgoCD | https://argocd.vosukula.online |
| Monitoring | Prometheus + Grafana | https://grafana.vosukula.online |
| App | Python Flask microservices | https://app.vosukula.online |
| Registry | AWS ECR | us-east-1 |

**Key config:**
- AWS Account: `589389425618`
- Region: `us-east-1`
- EKS Cluster: `expense-dev`
- Domain: `vosukula.online`
- ACM Wildcard Cert ARN: `arn:aws:acm:us-east-1:589389425618:certificate/483235ba-eb66-4a81-b2ab-6244c3f2a2d6`

---

## Prerequisites

- AWS CLI configured (`aws configure`)
- Terraform >= 1.10 installed
- Git Bash (Windows)
- `helm.exe` and `kubectl.exe` in repo root (downloaded by script 01)

---

## Step 1 — Terraform Infrastructure

```bash
cd Terraform

# Initialize
terraform init -backend-config=tfvars/dev/backend.tfvars

# Plan
terraform plan -var-file=tfvars/dev/dev.tfvars

# Apply
terraform apply -var-file=tfvars/dev/dev.tfvars
```

**What this creates:**
- VPC with public/private/database subnets
- EKS cluster `expense-dev` (Kubernetes 1.33)
- ECR repositories: `order-service`, `payment-service`, `user-service`
- IAM roles: node group, EBS CSI, ALB controller
- S3 backend + DynamoDB state locking

⚠️ Takes ~15 minutes to complete.

---

## Step 2 — Install Tools + Configure kubectl

```bash
cd ..  # back to repo root
bash scripts/01-install-tools.sh
```

**What this does:**
- Downloads `helm.exe` to repo root
- Downloads `kubectl.exe` to repo root
- Runs `aws eks update-kubeconfig` for `expense-dev`
- Verifies cluster connectivity with `kubectl get nodes`

**Verify:**
```bash
./kubectl.exe get nodes
# Should show 2 nodes in Ready state
```

---

## Step 3 — Install AWS Load Balancer Controller

```bash
bash scripts/02-install-alb-controller.sh
```

**What this does:**
- Adds `eks` Helm repo
- Installs `aws-load-balancer-controller` in `kube-system` namespace
- Uses IAM role: `expense-dev-alb-controller-role`

**Verify:**
```bash
./kubectl.exe get pods -n kube-system | grep aws-load-balancer
# Should show 2 pods Running
```

---

## Step 4 — Install Jenkins

### 4a. Create Jenkins admin secret FIRST
```bash
./kubectl.exe create secret generic jenkins-admin-secret \
  --from-literal=jenkins-admin-user=admin \
  --from-literal=jenkins-admin-password=YOUR_PASSWORD \
  -n jenkins
```
⚠️ **Do this before running the install script** — if the secret is missing, Jenkins pod will be stuck in `Init:0/2` indefinitely.

### 4b. Run install script
```bash
bash scripts/03-install-jenkins.sh
```

### 4c. Watch pod startup
```bash
./kubectl.exe get pods -n jenkins -w
```
Expected progression:
```
Init:0/2  →  Init:1/2  →  Init:2/2  →  Running
```
- `Init:1/2` takes ~1 min (secret/volume mount)
- `Init:2/2` takes ~3-5 min (plugin downloads)

### 4d. Apply Jenkins ingress
```bash
./kubectl.exe apply -f kubernetes/ingress/jenkins-ingress.yaml
```

### 4e. Verify
```bash
./kubectl.exe get ingress -n jenkins
# ADDRESS field should populate within 3-5 minutes
```

Update Route53 CNAME for `jenkins.vosukula.online` to point to the ALB address shown.

**Access:** https://jenkins.vosukula.online  
**Username:** `admin`  
**Password:** whatever you set in step 4a

---

## Step 5 — Install ArgoCD

```bash
bash scripts/04-install-argocd.sh
```

**What this does:**
- Creates `argocd` namespace
- Installs ArgoCD using `--server-side` flag (required for large CRDs)
- Waits for all deployments to be available
- Applies ArgoCD ingress

**Verify:**
```bash
./kubectl.exe get pods -n argocd
./kubectl.exe get ingress -n argocd
```

**Get ArgoCD initial admin password:**
```bash
./kubectl.exe get secret argocd-initial-admin-secret \
  -n argocd \
  -o jsonpath="{.data.password}" | base64 -d
```

**Access:** https://argocd.vosukula.online  
**Username:** `admin`  
**Password:** output from above command

---

## Step 6 — Install Monitoring (Prometheus + Grafana)

### 6a. Create Grafana admin secret FIRST
```bash
./kubectl.exe create secret generic grafana-admin-secret \
  --from-literal=admin-user=admin \
  --from-literal=admin-password=YOUR_PASSWORD \
  -n monitoring
```

### 6b. Run install script
```bash
bash scripts/05-install-monitoring.sh
```

### 6c. Apply Grafana ingress
```bash
./kubectl.exe apply -f kubernetes/ingress/grafana-ingress.yaml
```

**Access:** https://grafana.vosukula.online  
**Username:** `admin`  
**Password:** whatever you set in step 6a

---

## Step 7 — Connect Jenkins Agent (EC2)

The `jenkins-agent` EC2 instance (`cicd-tools` repo) connects as a build agent.

### 7a. In Jenkins UI — Create the Node
1. Manage Jenkins → Nodes → **New Node**
2. Name: `jenkins-agent`
3. Type: **Permanent Agent**
4. Click Create
5. Configure:
   - Labels: `AGENT`
   - Remote root directory: `/home/ec2-user/jenkins-agent`
   - Launch method: **Launch agent by connecting it to the controller**
   - ⚠️ Check **"Use WebSocket"**
6. Save

Jenkins will show a command with a **secret token** — copy it.

### 7b. On the Agent EC2 — Connect to Jenkins

SSH into the agent instance:
```bash
ssh -i /c/Devops/dev-ops-key.pem ec2-user@<jenkins-agent-public-ip>
```

Create work directory and download agent.jar:
```bash
mkdir -p /home/ec2-user/jenkins-agent
curl -k -sLO https://jenkins.vosukula.online/jnlpJars/agent.jar
ls -la agent.jar  # should be ~1.5MB, not 0 bytes
```

⚠️ **Important:** The URL in the Jenkins UI shows `http://jenkins:8080` — that's the internal Kubernetes service name. Replace it with `https://jenkins.vosukula.online/` since the EC2 agent is outside the cluster.

Run the connect command:
```bash
java -jar agent.jar \
  -url https://jenkins.vosukula.online/ \
  -secret <SECRET_FROM_JENKINS_UI> \
  -name "jenkins-agent" \
  -webSocket \
  -workDir "/home/ec2-user/jenkins-agent"
```

You should see:
```
INFO: Connected
```

In Jenkins UI, the node will flip from `(offline)` → **online** (green circle).

### 7c. Keep Agent Running Permanently

The above command stops when you close SSH. Run it in background instead:
```bash
nohup java -jar agent.jar \
  -url https://jenkins.vosukula.online/ \
  -secret <SECRET_FROM_JENKINS_UI> \
  -name "jenkins-agent" \
  -webSocket \
  -workDir "/home/ec2-user/jenkins-agent" > ~/jenkins-agent.log 2>&1 &

echo "Agent PID: $!"
```

To check if it's running later:
```bash
ps aux | grep agent.jar
cat ~/jenkins-agent.log
```

To stop it:
```bash
kill $(pgrep -f agent.jar)
```

### 7d. Add AWS Credentials in Jenkins
1. Go to: `https://jenkins.vosukula.online/manage/credentials/store/system/domain/_/newCredentials`
2. Kind: **AWS Credentials**
3. ID: `aws-credentials`
4. Description: `aws-cred`
5. Access Key ID: from AWS IAM Console → Users → Security credentials → Create access key
6. Secret Access Key: shown once during creation — save it

⚠️ If the "Add" popup doesn't work in the pipeline config page, add credentials directly via the URL above first, then return to the pipeline config — it will appear in the dropdown.

### 7e. Troubleshooting Agent Connection

| Issue | Fix |
|---|---|
| `Unable to access jarfile agent.jar` | File is 0 bytes — re-download with `curl -k -sLO` |
| SSL mismatch error on curl | Use `-k` flag or wait for wildcard cert to propagate |
| Agent shows offline after connecting | Check node label is `AGENT` (case-sensitive) |
| Agent disconnects when SSH closes | Use `nohup` command (step 7c) |
| `Connection refused` on port 8080 | Replace `http://jenkins:8080` with `https://jenkins.vosukula.online/` |

---

## Step 8 — Configure Jenkins Pipeline

1. New Item → Pipeline
2. Pipeline script from SCM
3. SCM: Git
4. URL: `https://github.com/ShivaKrishna44/devops-microservices-platform.git`
5. Credentials: none (public repo) or GitHub PAT if private
6. Branch: `main`
7. Script path: `Jenkinsfile`

**Run pipeline:**
- Select service: `order-service` / `payment-service` / `user-service`
- Set image tag or leave as `latest`

---

## Route53 DNS Records

All DNS is managed by the ALB Ingress Controller via CNAME records.

| Subdomain | Points to |
|---|---|
| `jenkins.vosukula.online` | ALB CNAME from `kubectl get ingress -n jenkins` |
| `argocd.vosukula.online` | ALB CNAME from `kubectl get ingress -n argocd` |
| `grafana.vosukula.online` | ALB CNAME from `kubectl get ingress -n monitoring` |
| `app.vosukula.online` | ALB CNAME from `kubectl get ingress -n default` |

⚠️ Do NOT create A records for these — the ALB controller owns the CNAMEs.

---

## Kubernetes Secrets Checklist

These must be created BEFORE running install scripts:

```bash
# Jenkins
./kubectl.exe create secret generic jenkins-admin-secret \
  --from-literal=jenkins-admin-user=admin \
  --from-literal=jenkins-admin-password=YOUR_PASSWORD \
  -n jenkins

# Grafana
./kubectl.exe create secret generic grafana-admin-secret \
  --from-literal=admin-user=admin \
  --from-literal=admin-password=YOUR_PASSWORD \
  -n monitoring
```

---

## Useful Commands

```bash
# Check all pods across namespaces
./kubectl.exe get pods -A

# Check ingress addresses
./kubectl.exe get ingress -A

# Check EKS nodes
./kubectl.exe get nodes

# Jenkins logs
./kubectl.exe logs jenkins-0 -n jenkins -c jenkins

# ArgoCD logs
./kubectl.exe logs -n argocd -l app.kubernetes.io/name=argocd-server

# Grafana logs
./kubectl.exe logs -n monitoring -l app.kubernetes.io/name=grafana

# ECR login
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin \
  589389425618.dkr.ecr.us-east-1.amazonaws.com

# Get Jenkins initial password (if secret-based setup wasn't used)
./kubectl.exe exec -n jenkins -it jenkins-0 -- \
  cat /var/jenkins_home/secrets/initialAdminPassword

# Get ArgoCD password
./kubectl.exe get secret argocd-initial-admin-secret \
  -n argocd -o jsonpath="{.data.password}" | base64 -d

# Restart a stuck pod
./kubectl.exe delete pod <pod-name> -n <namespace>
# StatefulSet and Deployment will auto-recreate it
```

---

## Common Issues & Fixes

| Issue | Fix |
|---|---|
| Jenkins pod stuck `Init:0/2` | Create `jenkins-admin-secret` then delete pod to restart |
| `CertificateNotFound` in ingress events | Replace `REPLACE_WITH_ACM_CERT_ARN` with real ARN and re-apply |
| SSL mismatch on subdomains | Use wildcard cert `*.vosukula.online` not apex `vosukula.online` |
| ArgoCD CRD too large error | Use `kubectl apply --server-side` |
| Helm timeout `context deadline exceeded` | Remove `--wait` from helm command, use `rollout status` separately |
| `deployment/jenkins not found` | Jenkins uses StatefulSet — use `rollout status statefulset/jenkins` |
| Route53 CNAME conflict with A record | ALB controller owns DNS — don't create A records in Terraform |
| `dnf makecache` hangs in user_data | Add `-y` flag: `dnf makecache -y` |
| `java-21-amazon-corretto` not found | Use `java-21-openjdk` on RHEL 9 |
| EKS access entry 409 conflict | Remove duplicate principal from `access_entries` — already handled by `enable_cluster_creator_admin_permissions` |
| ECR `latest` tag push fails (IMMUTABLE) | Don't push `:latest` to IMMUTABLE repos. Use unique tags only. Removed `latest` push from Jenkinsfile |
| Jenkins agent offline (disk space) | Node free disk < 1 GiB threshold. Set "Disk Space Monitoring Thresholds" → Free Disk Space Threshold to `100MiB` in node config. Or run `docker system prune -af` on agent |
| "Waiting for next available executor" | Abort stuck builds in queue. Or increase `# of executors` to 2 on the node |
| ACM cert only covers `vosukula.online` not subdomains | Request a wildcard cert: `aws acm request-certificate --domain-name "*.vosukula.online"`. Use that ARN in ingress files |

---

## Tomorrow's Remaining Steps

- [ ] Verify `https://jenkins.vosukula.online` works with new wildcard cert
- [ ] Connect jenkins-agent EC2 node (download agent.jar, run connect command)
- [ ] Run first pipeline build for one microservice
- [ ] Install monitoring: `bash scripts/05-install-monitoring.sh`
- [ ] Apply app ingress: `./kubectl.exe apply -f kubernetes/ingress/app-ingress.yaml`
- [ ] Set up ArgoCD applications for GitOps deployment

---

## Operations Dashboard — Status & Common Tasks

### Where to See Status

| What | Where | URL / Command |
|---|---|---|
| Pipeline builds | Jenkins UI | `https://jenkins.vosukula.online/job/devops-microservices-pipeline/` |
| GitOps deployments | ArgoCD UI | `https://argocd.vosukula.online/applications` |
| Cluster metrics | Grafana UI | `https://grafana.vosukula.online` |
| Code quality | SonarQube UI | `https://sonar.vosukula.online` |
| All pods | CLI | `./kubectl.exe get pods -A` |
| All ingresses/ALBs | CLI | `./kubectl.exe get ingress -A` |
| Node health | CLI | `./kubectl.exe get nodes` |
| ECR images | AWS Console | ECR → us-east-1 → Repositories |

### How to Build & Deploy a Service

1. Go to Jenkins: `https://jenkins.vosukula.online/job/devops-microservices-pipeline/`
2. Click **"Build with Parameters"**
3. Select: `SERVICE_NAME` (order/payment/user), `IMAGE_TAG` (e.g. `2.0`)
4. Click **Build**
5. Watch progress in Console Output
6. ArgoCD auto-syncs the new image if using GitOps mode

### How to Check ArgoCD Sync

1. Go to: `https://argocd.vosukula.online/applications`
2. Each app shows: **Healthy** (green) or **Degraded** (red)
3. Click an app to see pods, services, events
4. Click **SYNC** to manually force a resync

### How to View Grafana Dashboards

1. Go to: `https://grafana.vosukula.online`
2. Login: `admin` / your password
3. Left sidebar → Dashboards → Browse
4. Pre-built: `Kubernetes / Compute Resources / Cluster`
5. Pod-level: `Kubernetes / Compute Resources / Pod`

### How to Check SonarQube

1. Go to: `https://sonar.vosukula.online`
2. Login: `admin` / `admin` (change on first login)
3. Projects tab → click a service → see bugs, vulnerabilities, code smells

### How to Check Canary/Blue-Green Rollouts

```bash
# View rollout status (after enabling rollout.enabled=true in values)
kubectl argo rollouts get rollout order-service -n order-service --watch

# Promote past a pause step
kubectl argo rollouts promote order-service -n order-service

# Abort and rollback
kubectl argo rollouts abort order-service -n order-service
```

### Quick CLI — Show Only Problem Pods

```bash
./kubectl.exe get pods -A | grep -v "Running\|Completed"
```

### Per-Namespace Status

```bash
./kubectl.exe get all -n order-service
./kubectl.exe get all -n payment-service
./kubectl.exe get all -n user-service
./kubectl.exe get all -n jenkins
./kubectl.exe get all -n argocd
./kubectl.exe get all -n monitoring
./kubectl.exe get all -n sonarqube
./kubectl.exe get all -n argo-rollouts
```
