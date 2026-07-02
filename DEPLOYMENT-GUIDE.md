# DevOps Microservices Platform — Complete Deployment Guide

A step-by-step guide to deploy the full platform from scratch.

---

## 📚 Documentation Map (Start Here)

| # | Document | Covers | When to Read |
|---|---|---|---|
| 1 | **DEPLOYMENT-GUIDE.md** (this file) | Steps 1–9: Infrastructure → Jenkins → ArgoCD → Monitoring → Agent → Pipeline → SonarQube | First — sets up the entire platform |
| 2 | **PHASES-IMPLEMENTATION.md** | Advanced details: Helm Charts, ArgoCD GitOps flow, Canary/Blue-Green Rollouts | After base platform is running — deep-dive into each phase |
| 3 | **TROUBLESHOOTING.md** | Every error encountered and how it was fixed | Reference when something breaks |

**Reading order:** Start with this file (DEPLOYMENT-GUIDE), follow Steps 1–9 to get the platform running end-to-end.

---

## 🚀 Quick Start — Full Platform in Order

Run these steps **sequentially**. Each step depends on the previous one.

```
Step 1: Terraform (EKS + VPC + ECR + IAM)         ← 15 min
Step 2: Tools (Helm + kubectl + kubeconfig)        ← 2 min
Step 3: ALB Controller                             ← 3 min
Step 4: Jenkins on EKS                             ← 5 min
Step 5: ArgoCD                                     ← 3 min
Step 6: Monitoring (Prometheus + Grafana)          ← 5 min
Step 7: Connect Jenkins Agent EC2                  ← 5 min
Step 8: Configure Pipeline + First Build           ← 5 min
Step 9: SonarQube                                  ← 10 min
```

**Total time from zero to working platform: ~50 minutes**

---

## 🛑 Teardown — Destroy Everything (in reverse order)

When you're done and want to stop costs, run these in **reverse order**:

```bash
# Step 1: Delete ArgoCD apps (stops deployments)
./kubectl.exe delete -f kubernetes/argocd/apps/

# Step 2: Uninstall Helm releases
./helm.exe uninstall sonarqube -n sonarqube
./helm.exe uninstall monitoring -n monitoring
./helm.exe uninstall jenkins -n jenkins

# Step 3: Delete Argo Rollouts
./kubectl.exe delete -f https://github.com/argoproj/argo-rollouts/releases/latest/download/install.yaml -n argo-rollouts

# Step 4: Delete ArgoCD
./kubectl.exe delete -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Step 5: Delete ALB controller
./helm.exe uninstall aws-load-balancer-controller -n kube-system

# Step 6: Delete all namespaces (cleans up remaining resources)
./kubectl.exe delete namespace sonarqube monitoring jenkins argocd argo-rollouts order-service payment-service user-service

# Step 7: Destroy Terraform infrastructure (EKS + VPC + ECR)
cd Terraform
terraform destroy -var-file=tfvars/dev/dev.tfvars

# Step 8: Destroy Jenkins EC2 instances (cicd-tools repo)
cd ../../../cicd-tools
terraform destroy
```

⚠️ `terraform destroy` deletes everything permanently — EKS cluster, VPC, ECR images, IAM roles. Only run when you're completely done.

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

> ⚠️ **Note:** Jenkins Agent setup comes in **Step 7** — do NOT try to connect an agent yet. Continue with ArgoCD and Monitoring first. Jenkins needs to be fully running with ingress/URL working before the agent can connect to it.

> 💡 **Certificate:** One wildcard ACM cert (`*.vosukula.online`) covers ALL subdomains — jenkins, argocd, grafana, sonar, app. You only need to generate ONE certificate. All ingress files share the same cert ARN.

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

### 6a. Create namespace and Grafana admin secret FIRST
```bash
# Create namespace first (secret can't exist without it)
./kubectl.exe create namespace monitoring --dry-run=client -o yaml | ./kubectl.exe apply -f -

# Now create the secret
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

### 6d. Add Route53 DNS for Grafana
```bash
# Get the ALB address
./kubectl.exe get ingress -n monitoring
# Copy the ADDRESS value
```
Then in AWS Console: Route53 → Hosted zones → `vosukula.online` → Create record:
- Record name: `grafana`
- Record type: CNAME
- Value: paste the ALB address from above
- TTL: 300
- Click Create

Wait 1-2 min for DNS to propagate.

**Access:** https://grafana.vosukula.online  
**Username:** `admin`  
**Password:** whatever you set in step 6a (or `changeme` if the script created it)

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
java -jar agent.jar -url https://jenkins.vosukula.online -secret  080698792ce62d22336fd216d8f2822b0676feeff1d0ac2c9db9de5affee2ccd -name "jenkins-agent" -webSocket -workDir "/home/ec2-user/jenkins-agent"

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

before SYNC - ./kubectl.exe apply -f kubernetes/argocd/apps/

$ ./kubectl.exe get applications -n argocd
NAME              SYNC STATUS   HEALTH STATUS
order-service     OutOfSync     Progressing
payment-service   OutOfSync     Progressing
user-service      OutOfSync     Progressing


### How to View Grafana Dashboards

1. Go to: `https://grafana.vosukula.online`
2. Login: `admin` / your password
3. Left sidebar → Dashboards → Browse
4. Pre-built: `Kubernetes / Compute Resources / Cluster`
5. Pod-level: `Kubernetes / Compute Resources / Pod`

### Import Pre-built Dashboards (recommended)

1. Dashboards → **Import** → enter Dashboard ID → Load → select `Prometheus` → Import

| Dashboard ID | Name | What It Shows |
|---|---|---|
| `15760` | Kubernetes Cluster Monitoring | Nodes, pods, CPU, memory overview |
| `13770` | Kubernetes Pod Metrics | Per-pod CPU, memory, network |
| `12006` | Kubernetes Deployment Metrics | Deployment replicas, rollout status |
| `1860` | Node Exporter Full | Detailed node-level metrics |

### Set Up Alerts in Grafana

1. Left sidebar → **Alerting** → **Alert rules** → **+ New alert rule**
2. Example alert queries:

| Alert | PromQL Query |
|---|---|
| Pod restarts > 3 in 5 min | `increase(kube_pod_container_status_restarts_total[5m]) > 3` |
| Node CPU > 80% | `100 - (avg by(instance)(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 80` |
| Pod not ready | `kube_pod_status_ready{condition="false"} == 1` |
| Disk usage > 85% | `(node_filesystem_size_bytes - node_filesystem_avail_bytes) / node_filesystem_size_bytes * 100 > 85` |

3. Set evaluation: every 1 min, fire after 5 min continuous breach
4. Add **Contact point**: Alerting → Contact points → + Add → Slack/Email/Webhook
5. Save

### Configure Slack Notifications (optional)

1. Create Slack incoming webhook: [Slack API](https://api.slack.com/messaging/webhooks)
2. Grafana → Alerting → Contact points → + Add contact point
3. Name: `slack-alerts`, Type: Slack, Webhook URL: paste
4. Test → Save
5. Assign contact point to your alert rules



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

---

## Step 9 — SonarQube Setup & Integration

### 9a. Access SonarQube
- URL: `https://sonar.vosukula.online`
- Default login: `admin` / `admin` (forced password change on first login)

### 9b. Create Project Token in SonarQube
1. Login → click avatar (top right) → **My Account**
2. Go to **Security** tab
3. Generate Token → name: `jenkins-sonar-token` → type: `Global Analysis Token`
4. Copy the token (shown only once)

### 9c. Install SonarQube Scanner Plugin in Jenkins
1. Jenkins → Manage Jenkins → **Plugins** → **Available plugins**
2. Search: `SonarQube Scanner`
3. Install it → restart Jenkins if prompted

### 9d. Add SonarQube Token to Jenkins Credentials
1. Manage Jenkins → Credentials → System → Global → Add Credentials
2. Kind: **Secret text**
3. Secret: paste the SonarQube token
4. ID: `sonar-token`
5. Description: `SonarQube Token`

### 9e. Configure SonarQube Server in Jenkins
⚠️ This option only appears AFTER installing the SonarQube Scanner plugin (step 9c)

1. Manage Jenkins → **System** → scroll to **SonarQube servers**
2. Check ✅ "Environment variables"
3. Click **"Add SonarQube"**
4. Name: `SonarQube`
5. Server URL: `https://sonar.vosukula.online`
6. Server authentication token: select `sonar-token` from dropdown
7. Save

### 9f. Install sonar-scanner on Jenkins Agent EC2
```bash
ssh -i /c/Devops/dev-ops-key.pem ec2-user@<agent-ip>

curl -fLO https://binaries.sonarsource.com/Distribution/sonar-scanner-cli/sonar-scanner-cli-5.0.1.3006-linux.zip
unzip sonar-scanner-cli-5.0.1.3006-linux.zip
sudo mv sonar-scanner-5.0.1.3006-linux /opt/sonar-scanner
sudo ln -s /opt/sonar-scanner/bin/sonar-scanner /usr/local/bin/sonar-scanner
sonar-scanner --version
```

### 9g. Test Manual Scan
```bash
cd ~/jenkins-agent/workspace/devops-microservices-pipeline/app/order-service

sonar-scanner \
  -Dsonar.projectKey=order-service \
  -Dsonar.sources=. \
  -Dsonar.host.url=https://sonar.vosukula.online \
  -Dsonar.token=<YOUR_TOKEN>
```

Check results at: `https://sonar.vosukula.online/projects`

### 9h. Automated SonarQube in Jenkinsfile
Once manual scan works, add this stage to Jenkinsfile (between Build & Docker stages):
```groovy
stage('SonarQube Analysis') {
    when { expression { !params.SKIP_SONAR } }
    steps {
        dir("app/${env.SERVICE_NAME}") {
            withSonarQubeEnv('SonarQube') {
                sh 'sonar-scanner -Dsonar.projectKey=${SERVICE_NAME}'
            }
        }
    }
}
```

---

## Step 10 — Deploy with Helm Charts

After pipeline builds succeed, deploy services using Helm charts (packaged deployments with rollback support).

### 10a. Test Helm chart locally
```bash
./helm.exe template order-service ./charts/microservice \
  -f charts/microservice/values-order.yaml \
  --set image.tag=latest11
```
If output looks correct (valid YAML), proceed.

### 10b. Deploy each service with Helm
```bash
# Order service
./helm.exe upgrade --install order-service ./charts/microservice \
  -f charts/microservice/values-order.yaml \
  --set image.tag=latest11 \
  -n order-service --create-namespace

# Payment service
./helm.exe upgrade --install payment-service ./charts/microservice \
  -f charts/microservice/values-payment.yaml \
  --set image.tag=latest12 \
  -n payment-service --create-namespace

# User service
./helm.exe upgrade --install user-service ./charts/microservice \
  -f charts/microservice/values-user.yaml \
  --set image.tag=latest14 \
  -n user-service --create-namespace
```

### 10c. Verify
```bash
./kubectl.exe get pods -n order-service
./kubectl.exe get pods -n payment-service
./kubectl.exe get pods -n user-service
```

---

## Step 11 — Wire ArgoCD to Helm Charts (GitOps)

ArgoCD watches Git and auto-deploys when Helm values change. No more manual `helm install`.

### 11a. Push charts to Git first
```bash
git add charts/ kubernetes/argocd/apps/
git commit -m "Add Helm charts and ArgoCD apps"
git push origin main
```

### 11b. Apply ArgoCD Application CRDs
```bash
./kubectl.exe apply -f kubernetes/argocd/apps/
```

### 11c. Verify in ArgoCD UI
Go to `https://argocd.vosukula.online/applications` — all 3 services should appear and sync.

```bash
./kubectl.exe get applications -n argocd
# Should show: order-service, payment-service, user-service
```

### 11d. How GitOps works now
```
Jenkins builds image → pushes to ECR
  → Updates image tag in charts/microservice/values-<service>.yaml
  → Commits and pushes to Git
  → ArgoCD detects change → auto-deploys to EKS
```

No more `kubectl apply` or `helm install` from pipeline — ArgoCD handles deployment.

---

## Step 12 — Install Argo Rollouts (Canary/Blue-Green)

### 12a. Run install script
```bash
bash scripts/07-install-argo-rollouts.sh
```

### 12b. Verify
```bash
./kubectl.exe get pods -n argo-rollouts
```

### 12c. Enable canary for a service
Edit `charts/microservice/values-order.yaml`:
```yaml
rollout:
  enabled: true
  strategy: canary
```

Push to Git → ArgoCD deploys using Rollout CRD instead of Deployment.

### 12d. Monitor rollout
```bash
kubectl argo rollouts get rollout order-service -n order-service --watch
```

---

## ✅ Platform Complete!

All steps done. Your platform now has:

| Component | Status | Access |
|---|---|---|
| EKS Cluster | Running | `kubectl get nodes` |
| Jenkins CI/CD | Running | `https://jenkins.vosukula.online` |
| ArgoCD GitOps | Synced | `https://argocd.vosukula.online` |
| Grafana Monitoring | Running | `https://grafana.vosukula.online` |
| SonarQube | Running | `https://sonar.vosukula.online` |
| Argo Rollouts | Installed | Ready for canary/blue-green |
| Helm Charts | Ready | `charts/microservice/` |
| 3 Microservices | Deployed | order, payment, user |

**Next steps (optional):**
- Add Slack notifications to Jenkins pipeline
- Configure Alertmanager to send alerts to Slack/email
- Set up Grafana dashboards per service
- Add network policies between namespaces
- Move to `PHASES-IMPLEMENTATION.md` for deep-dive into each phase


---

## Step 13 — Verify Microservice Functionality

After deployment, verify all 3 services are responding correctly.

---

### Available Endpoints

| Service | Endpoint | Returns |
|---|---|---|
| order-service | `GET /` | `{"service": "order-service", "status": "running"}` |
| order-service | `GET /orders` | List of orders (id, item, quantity, status) |
| payment-service | `GET /` | `{"service": "payment-service", "status": "running"}` |
| payment-service | `GET /payments` | List of payments (id, amount, status) |
| user-service | `GET /` | `{"service": "user-service", "status": "running"}` |
| user-service | `GET /users` | List of users (id, name) |

All services run Flask on port 5000. The `/` endpoint is a health check.

---

### Option 1: Test Locally (without deploying)

```bash
cd app/order-service
pip install -r requirements.txt
python app.py
# App starts on http://localhost:5000
```

```bash
curl http://localhost:5000/
# {"service": "order-service", "status": "running"}

curl http://localhost:5000/orders
# [{"order_id": 1001, "item": "Laptop", ...}, ...]
```

---

### Option 2: Test via Docker

```bash
cd app/order-service
docker build -t order-service:test .
docker run -p 5000:5000 order-service:test
```

```bash
curl http://localhost:5000/
curl http://localhost:5000/orders
```

---

### Option 3: Test on EKS via Ingress (Public URL)

The `app-ingress.yaml` routes traffic by path prefix on `app.vosukula.online`:

```bash
# Order service
curl https://app.vosukula.online/order
curl https://app.vosukula.online/order/orders

# Payment service
curl https://app.vosukula.online/payment
curl https://app.vosukula.online/payment/payments

# User service
curl https://app.vosukula.online/user
curl https://app.vosukula.online/user/users
```

---

### Option 4: Test on EKS via Port-Forward (no ingress needed)

```bash
# Forward local port to cluster service
kubectl port-forward svc/order-service 5000:5000 -n order-service

# In another terminal:
curl http://localhost:5000/
curl http://localhost:5000/orders
```

Repeat for payment-service and user-service.

---

### Option 5: Test from Inside the Cluster

```bash
# Exec into any running pod and curl another service:
kubectl exec -it <any-pod> -- curl http://order-service.order-service.svc.cluster.local:5000/orders
kubectl exec -it <any-pod> -- curl http://payment-service.payment-service.svc.cluster.local:5000/payments
kubectl exec -it <any-pod> -- curl http://user-service.user-service.svc.cluster.local:5000/users
```

---

### Quick Validation Script (test all at once)

```bash
echo "=== Order Service ==="
curl -s https://app.vosukula.online/order | python -m json.tool

echo "=== Payment Service ==="
curl -s https://app.vosukula.online/payment | python -m json.tool

echo "=== User Service ==="
curl -s https://app.vosukula.online/user | python -m json.tool
```

If all return JSON with `"status": "running"` — services are healthy. ✅

---

### Troubleshooting App Issues

| Problem | Debug | Fix |
|---|---|---|
| `curl` returns 404 | Check ingress path routing matches app routes | Verify `app-ingress.yaml` paths |
| `curl` returns 502/503 | Pod not running or health check failing | `kubectl get pods -n order-service` |
| Connection timeout | Ingress not created or DNS not pointing to ALB | `kubectl get ingress` + check Route53 |
| JSON not returned | Wrong port or app crashed | `kubectl logs <pod> -n order-service` |
| Works via port-forward but not ingress | ALB or DNS issue, not app issue | Check ALB target health + ingress events |
