# Complete Platform Flow (one picture)

The whole `DEPLOYMENT-GUIDE.md` as a single diagram: infrastructure, cluster add-ons, the Jenkins
CI/CD pipeline, ArgoCD GitOps, and monitoring. Read it top to bottom. Each numbered block is a phase
you set up once, except the CI/CD loop, which runs on every change.

Project facts: AWS account `589389425618`, region `us-east-1`, cluster `expense-dev` (Kubernetes 1.33),
domain `vosukula.online`, ECR repos `order-service` / `payment-service` / `user-service`.

```
==============================================================================================
 PHASE 1 - INFRASTRUCTURE (Terraform, run once)                                      ~15 min
==============================================================================================
  terraform init -backend-config=tfvars/dev/backend.tfvars
  terraform apply -var-file=tfvars/dev/dev.tfvars
        |
        v
  +--------------------------------------------------------------------------------------+
  |  AWS account 589389425618, region us-east-1                                          |
  |                                                                                      |
  |  VPC  ->  public subnets (ALB)                                                       |
  |          private subnets (EKS nodes)                                                 |
  |          database subnets                                                            |
  |                                                                                      |
  |  EKS cluster "expense-dev"  ->  managed node group (2 x nodes)                       |
  |  ECR repos: order-service, payment-service, user-service                             |
  |  IAM roles: node group, EBS CSI (IRSA), ALB controller (IRSA)                        |
  |  State: S3 bucket + DynamoDB lock table                                              |
  +--------------------------------------------------------------------------------------+
        |
        |  aws eks update-kubeconfig --name expense-dev --region us-east-1
        v
==============================================================================================
 PHASE 2 - CLUSTER ADD-ONS (Helm + manifests, run once)                              ~20 min
==============================================================================================
  +------------------------+   +------------------------+   +------------------------+
  | AWS LB Controller      |   | Jenkins (StatefulSet)  |   | ArgoCD                 |
  | ns: kube-system        |   | ns: jenkins            |   | ns: argocd             |
  | (makes ALBs from       |   | jenkins.vosukula.online|   | argocd.vosukula.online |
  |  Ingress objects)      |   +------------------------+   +------------------------+
  +------------------------+   +------------------------+   +------------------------+
                               | Prometheus + Grafana   |   | SonarQube              |
                               | ns: monitoring         |   | ns: sonarqube          |
                               | grafana.vosukula.online|   | sonar.vosukula.online  |
                               +------------------------+   +------------------------+
                               | Argo Rollouts          |
                               | ns: argo-rollouts      |
                               +------------------------+
        |
        v
==============================================================================================
 PHASE 3 - CI JOB (Jenkins, runs on every push / build)
==============================================================================================
  +------------------------------------------------------------------------------------------+
  |                                                                                          |
  |   GitHub ---- pull code ----> Jenkins CI ---- dependency ----> OWASP                     |
  |     ^                              |          (dependency check)  |                      |
  |     | push code                   | docker build & push     code + quality              |
  |     |                             v                          gate analysis              |
  |  Developer                      Docker <---- build/push ----> SonarQube                  |
  |                                    ^                                                     |
  |                                    | image                                              |
  |                                 Trivy  (filesystem / image scan)                         |
  |                                                                                          |
  |   agent: EC2 box, label AGENT, has Docker + AWS CLI. Image pushed to ECR.                |
  +------------------------------------|-----------------------------------------------------+
                                       | trigger CD job
                                       v
==============================================================================================
 PHASE 4 - CD JOB + GITOPS (Jenkins writes to Git, ArgoCD deploys)
==============================================================================================
  +------------------------------------------------------------------------------------------+
  |                                                                                          |
  |   Jenkins CD --- update image tag ---> GitHub --- pull ---> Argo CD                      |
  |   (edits charts/microservice/values-<svc>.yaml, commits "[skip ci]")       |            |
  |                                                                            | deploy      |
  |                                                                            v             |
  |                                                             Kubernetes (EKS expense-dev) |
  |                                                             ns: order / payment / user   |
  |                                                             Deployment or Rollout        |
  |                                                             image pulled from ECR        |
  +------------------------------------------------------------------------------------------+
        |
        v  inbound traffic
  User browser -> Route 53 (*.vosukula.online) -> ALB -> Ingress app.vosukula.online
                  /order -> order-service,  /payment -> payment-service,  /user -> user-service
        |
        v
==============================================================================================
 PHASE 5 - MONITORING + FEEDBACK (always on)
==============================================================================================
  +------------------------------------------------------------------------------------------+
  |                                                                                          |
  |   Kubernetes pods ---- metrics ----> Prometheus ---- data ----> Grafana                  |
  |                                                                    |                     |
  |                                                                    | alert               |
  |                                                                    v                     |
  |                                                        Email / Slack  -> Developer       |
  |                                                                                          |
  +------------------------------------------------------------------------------------------+

  HANDOVER (the key idea): CI ends by committing the image tag to Git. ArgoCD starts by
  reading that Git change. Push-based CI, pull-based CD. Jenkins never runs kubectl apply.
```

## Setup steps per phase

Each phase matches a block in the picture above. Full detail and troubleshooting are in
`DEPLOYMENT-GUIDE.md`. This is the short, ordered version.

### Phase 1 - Infrastructure (Terraform, once)

```bash
cd Terraform
terraform init -backend-config=tfvars/dev/backend.tfvars
terraform plan  -var-file=tfvars/dev/dev.tfvars
terraform apply -var-file=tfvars/dev/dev.tfvars
terraform output          # note the ALB controller role ARN

aws eks update-kubeconfig --name expense-dev --region us-east-1
kubectl get nodes         # expect 2 nodes Ready
```

Creates the VPC, EKS, the node group, ECR, the IAM roles, and the S3 and DynamoDB state. The S3
bucket and lock table in `backend.tfvars` must already exist; Terraform's backend does not make them.

### Phase 2 - Cluster add-ons (Helm + manifests, once)

```bash
# AWS Load Balancer Controller (needed for every Ingress)
helm repo add eks https://aws.github.io/eks-charts && helm repo update
helm install aws-load-balancer-controller eks/aws-load-balancer-controller \
  -n kube-system -f alb-controller-values.yaml      # set clusterName and the role ARN first

# Secrets BEFORE the install scripts, or pods hang in Init
kubectl create secret generic jenkins-admin-secret \
  --from-literal=jenkins-admin-user=admin --from-literal=jenkins-admin-password=<pw> -n jenkins
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic grafana-admin-secret \
  --from-literal=admin-user=admin --from-literal=admin-password=<pw> -n monitoring

# Install each add-on
bash scripts/03-install-jenkins.sh
bash scripts/04-install-argocd.sh
bash scripts/05-install-monitoring.sh
bash scripts/07-install-argo-rollouts.sh
# SonarQube per DEPLOYMENT-GUIDE Step 9

# Ingress + DNS
kubectl apply -f kubernetes/ingress/
kubectl get ingress -A     # copy each ALB address into a Route 53 CNAME
```

One wildcard ACM cert `*.vosukula.online` covers jenkins, argocd, grafana, sonar and app.
Do not create A records for these; the ALB controller owns the CNAMEs.

### Phase 3 - CI job (Jenkins)

Connect an agent labeled `AGENT` (EC2 with Docker and the AWS CLI), add AWS and SonarQube
credentials, then create a Pipeline job from this repo's `Jenkinsfile`. The CI stages and how to add
OWASP, SonarQube, Docker and Trivy are in `JENKINS-CICD-FLOW.md`. Output: a scanned image in ECR.

### Phase 4 - CD job + GitOps (ArgoCD)

```bash
# Create the ArgoCD apps once; after that ArgoCD watches Git on its own
kubectl apply -f kubernetes/argocd/apps/
kubectl get applications -n argocd   # order-service, payment-service, user-service
```

The CD stage edits `charts/microservice/values-<svc>.yaml` with the new image tag, commits with
`[skip ci]`, and pushes. ArgoCD syncs the change to EKS. See `JENKINS-CICD-FLOW.md` step 5.

First release of each service is done by hand once (ArgoCD then takes over updates):

```bash
helm upgrade --install order-service charts/microservice \
  -f charts/microservice/values-order.yaml --set image.tag=<tag> -n order-service --create-namespace
# repeat for payment and user
```

### Phase 5 - Monitoring + feedback (always on)

- Prometheus scrapes pods and nodes. Grafana shows dashboards and fires alerts.
- Import Grafana dashboards by ID: `15760` cluster, `13770` pods, `1860` node exporter.
- Add alert rules (pod restarts, node CPU, pod not ready) and a contact point (email or Slack).
- Add an email `post` block to the Jenkinsfile so each build reports success or failure
  (`JENKINS-CICD-FLOW.md` step 8).

## Teardown (reverse order, to avoid cost)

```bash
kubectl delete -f kubernetes/argocd/apps/         # stop deployments first
helm uninstall order-service payment-service user-service
helm uninstall sonarqube -n sonarqube
helm uninstall monitoring -n monitoring
helm uninstall jenkins -n jenkins
helm uninstall aws-load-balancer-controller -n kube-system
kubectl delete -f kubernetes/ingress/             # remove Ingress so ALBs are released
cd Terraform && terraform destroy -var-file=tfvars/dev/dev.tfvars
```

Remove the Ingress objects before `terraform destroy`, or orphaned ALBs stay behind after the
cluster is gone.

## One-line summary of the whole flow

Terraform builds the cluster and registry. Helm installs Jenkins, ArgoCD, monitoring and SonarQube.
Jenkins builds and scans an image (OWASP, SonarQube, Trivy) and pushes it to ECR, then writes the new
image tag to Git. ArgoCD sees the Git change and deploys the Helm chart to EKS. Route 53 and the ALB
route users to the service. Prometheus and Grafana watch it and alert by email.

## Where the YAML files and Helm charts fit in the flow

There are two kinds of YAML in this repo, and they enter the flow at different phases.

- **Platform YAML** (`kubernetes/`): raw manifests for the tools (Jenkins, ArgoCD, monitoring,
  SonarQube, ingress, namespaces). You `kubectl apply` these by hand in Phase 2.
- **Application charts** (`charts/microservice/`): one Helm chart that templates every microservice.
  It is deployed by Helm the first time, then by ArgoCD on every update in Phase 4.

### The two folders

```
kubernetes/                         # PLATFORM manifests (applied with kubectl in Phase 2)
  namespaces/                       # creates the namespaces first
  jenkins/                          # Jenkins StatefulSet, service, PVC
  argocd/
    argocd-ingress.yaml             # ArgoCD UI ingress
    apps/
      order-service.yaml            # ArgoCD Application  -> points at the chart in Git
      payment-service.yaml          # ArgoCD Application
      user-service.yaml             # ArgoCD Application
  monitoring/                       # Prometheus + Grafana values/manifests
  sonarqube/                        # SonarQube manifests
  ingress/
    app-ingress.yaml                # app.vosukula.online  -> order/payment/user
    jenkins-ingress.yaml
    grafana-ingress.yaml
    sonarqube-ingress.yaml

charts/microservice/                # APPLICATION Helm chart (one chart, all 3 services)
  Chart.yaml
  values.yaml                       # shared defaults
  values-order.yaml                 # per-service values (image repo, tag, port, path)
  values-payment.yaml
  values-user.yaml
  templates/
    deployment.yaml                 # the Deployment (normal path)
    service.yaml                    # the Service
    hpa.yaml                        # autoscaler
    rollout.yaml                    # Argo Rollout (canary/blue-green path)
    canary-service.yaml             # canary traffic service
    preview-service.yaml            # preview service for blue-green
    _helpers.tpl                    # name/label helpers
```

### Where each one enters the flow

```
PHASE 2 (apply platform YAML with kubectl)
  kubernetes/namespaces/      --> creates namespaces (do this first)
  kubernetes/jenkins/         --> Jenkins
  kubernetes/argocd/          --> ArgoCD (not the apps/ yet)
  kubernetes/monitoring/      --> Prometheus + Grafana
  kubernetes/sonarqube/       --> SonarQube
  kubernetes/ingress/         --> ALBs for the tool UIs and the app

PHASE 3 (CI): no YAML changes. Jenkins only builds and pushes the image to ECR.

PHASE 4 (CD + GitOps): this is where the application chart is used
  step 1  Jenkins CD edits the image tag in:
            charts/microservice/values-<svc>.yaml   (tag: <new build tag>)
          then commits to Git with [skip ci]
  step 2  ArgoCD Application in kubernetes/argocd/apps/<svc>.yaml points at
            the chart path charts/microservice + the values-<svc>.yaml file
  step 3  ArgoCD renders the chart (templates/ + values) and applies the result:
            - normal mode  -> templates/deployment.yaml + service.yaml + hpa.yaml
            - canary mode  -> templates/rollout.yaml + canary-service.yaml + preview-service.yaml
          to EKS, in namespace order-service / payment-service / user-service

  First release only: you run `helm upgrade --install` with the same chart and values by hand.
  After that, every update goes Git -> ArgoCD, never helm by hand.
```

### Who applies what (important distinction)

| YAML | Applied by | When | How |
|------|-----------|------|-----|
| `kubernetes/namespaces,jenkins,argocd,monitoring,sonarqube,ingress` | You | Phase 2, once | `kubectl apply -f` |
| `kubernetes/argocd/apps/*.yaml` (ArgoCD Applications) | You | Phase 4, once | `kubectl apply -f kubernetes/argocd/apps/` |
| `charts/microservice/` (the app) first release | You | Phase 4, once per service | `helm upgrade --install` |
| `charts/microservice/` (the app) every update after | ArgoCD | Phase 4, every change | ArgoCD renders the chart and applies it |
| `charts/microservice/values-<svc>.yaml` image tag | Jenkins CD | Phase 4, every build | `sed` edit + git commit |

### The key point

The ArgoCD Application file (`kubernetes/argocd/apps/<svc>.yaml`) is the bridge. It tells ArgoCD two
things: the chart to use (`charts/microservice`) and the values file (`values-<svc>.yaml`). So when
Jenkins changes the image tag inside that values file in Git, ArgoCD notices, re-renders the chart,
and applies the new Deployment or Rollout. The chart turns one set of templates plus a values file
into the real Kubernetes objects (Deployment, Service, HPA, or Rollout).

## Browser request flow (what a URL touches)

When you type a host like `jenkins.vosukula.online` in a browser, the request passes through the same
chain every time. Only the last hop (which Service and pod) differs per host. This is the inbound path,
the reverse of how the platform was built.

```
                       You type a URL in the browser
                                   |
                                   v
  +----------------------------------------------------------------------+
  | 1. DNS - Route 53                                                     |
  |    *.vosukula.online is a CNAME to the ALB DNS name                   |
  |    (the ALB controller created the record from the Ingress)          |
  +----------------------------------------------------------------------+
                                   |  resolves to the ALB address
                                   v
  +----------------------------------------------------------------------+
  | 2. ALB (Application Load Balancer, in the public subnets)            |
  |    - listens on 443                                                   |
  |    - ends TLS using the wildcard ACM cert *.vosukula.online          |
  |    - made by the AWS Load Balancer Controller (ns: kube-system)      |
  +----------------------------------------------------------------------+
                                   |  forwards by host header
                                   v
  +----------------------------------------------------------------------+
  | 3. Ingress rule (host-based routing)                                 |
  |    each host maps to one Service in one namespace                    |
  +----------------------------------------------------------------------+
                                   |
                                   v
  +----------------------------------------------------------------------+
  | 4. Service (ClusterIP)  ->  5. Pod (the actual app)                  |
  +----------------------------------------------------------------------+
```

### Which host touches which modules

```
  jenkins.vosukula.online
     Route 53 -> ALB -> Ingress (kubernetes/ingress/jenkins-ingress.yaml)
        -> Service jenkins -> Pod jenkins-0            ns: jenkins

  argocd.vosukula.online
     Route 53 -> ALB -> Ingress (kubernetes/argocd/argocd-ingress.yaml)
        -> Service argocd-server -> Pod argocd-server  ns: argocd

  grafana.vosukula.online
     Route 53 -> ALB -> Ingress (kubernetes/ingress/grafana-ingress.yaml)
        -> Service grafana -> Pod grafana              ns: monitoring

  sonar.vosukula.online
     Route 53 -> ALB -> Ingress (kubernetes/ingress/sonarqube-ingress.yaml)
        -> Service sonarqube-sonarqube -> Pod          ns: sonarqube

  app.vosukula.online  (the microservices, path-based)
     Route 53 -> ALB -> Ingress (kubernetes/ingress/app-ingress.yaml)
        /order   -> Service order-service   -> Pod     ns: order-service
        /payment -> Service payment-service -> Pod     ns: payment-service
        /user    -> Service user-service    -> Pod     ns: user-service
```

Argo Rollouts has no host of its own. It is a controller in `ns: argo-rollouts`, not a web app. You
reach it through the ArgoCD UI, or with the CLI `kubectl argo rollouts get rollout <svc> -n <ns>`.

### The whole path as one table

| Hop | Module | Namespace | Config file |
|-----|--------|-----------|-------------|
| 1. DNS | Route 53 CNAME | n/a (AWS) | created by the ALB controller from the Ingress |
| 2. Load balancer + TLS | ALB + ACM cert | made in AWS | the Ingress annotations; cert `*.vosukula.online` |
| 3. Routing | Ingress (host or path rule) | same ns as the Service | `kubernetes/ingress/*` and `kubernetes/argocd/argocd-ingress.yaml` |
| 4. Stable address | Service (ClusterIP) | per app | the add-on manifests, or the chart `templates/service.yaml` for the apps |
| 5. The app | Pod | per app | the add-on manifests, or the chart `templates/deployment.yaml` |

### Points worth remembering

- **One ALB, one cert, many hosts.** The ALB controller can put several Ingress rules behind one ALB.
  The single wildcard cert `*.vosukula.online` covers every subdomain, so you request it once.
- **Host header decides the target.** The ALB and Ingress read the host name in the request and send
  it to the matching Service. `app.vosukula.online` is the exception: it routes by path, not host.
- **TLS ends at the ALB.** The browser-to-ALB hop is HTTPS. The ALB-to-pod hop is inside the VPC.
- **It is the build order reversed.** You built it bottom up (pod, Service, Ingress, ALB, DNS). A
  request comes top down (DNS, ALB, Ingress, Service, pod). If a URL fails, test it in that order.

### If a URL does not load, check in this order

```
nslookup jenkins.vosukula.online     # 1. does DNS resolve to the ALB?  (Route 53 CNAME)
kubectl get ingress -A               # 2. does the Ingress have an ADDRESS?  (ALB made?)
kubectl get svc -n <namespace>       # 3. does the Service exist and have endpoints?
kubectl get endpoints <svc> -n <ns>  # 4. are there ready pod IPs behind it?
kubectl get pods -n <namespace>      # 5. is the pod Running and Ready?
```

The first empty or failing result is the broken hop.

## How Jenkins interacts with AWS

Jenkins itself does not have AWS powers. The **Jenkins agent** (the EC2 box labeled `AGENT`) runs every
`sh` step, and those steps call the AWS CLI. So the agent's AWS credentials are the link between Jenkins
and AWS. Three AWS touch points appear in the `Jenkinsfile`:

```
  +----------------------------------------------------------------------+
  | Jenkins controller (ns: jenkins, in EKS)                             |
  |   schedules the job, sends the Jenkinsfile stages to the agent       |
  +----------------------------------------------------------------------+
                                   |  runs every sh step here
                                   v
  +----------------------------------------------------------------------+
  | Jenkins agent (EC2, outside the cluster)                             |
  |   has: Docker, AWS CLI, kubectl                                      |
  |   auth: AWS credentials (see "How the agent authenticates" below)   |
  +----------------------------------------------------------------------+
        |                          |                          |
        | (1) STS                  | (2) ECR                  | (3) EKS
        v                          v                          v
  +--------------+        +------------------+        +----------------------+
  | AWS STS      |        | Amazon ECR       |        | Amazon EKS           |
  | who am I?    |        | login, create,   |        | update-kubeconfig,   |
  | -> Account ID|        | push image       |        | then kubectl to API  |
  +--------------+        +------------------+        +----------------------+
```

### The three AWS calls in this Jenkinsfile

1. **STS - identity.** The `environment` block runs
   `aws sts get-caller-identity --query Account` to read the account id and build the ECR registry URL.
   This proves the agent has working AWS credentials before anything else.

2. **ECR - image registry.** In "Docker Build & Push":
   - `aws ecr get-login-password | docker login ...` logs Docker in to ECR (the token lasts 12 hours).
   - `aws ecr describe-repositories || aws ecr create-repository` makes the repo if it is missing.
   - `docker push` sends the image.

3. **EKS - the cluster.** In "Deploy to EKS":
   - `aws eks update-kubeconfig --name expense-dev` writes a kubeconfig on the agent. This is the AWS
     call. It asks EKS for the cluster endpoint and sets up IAM-based auth.
   - After that, `kubectl` talks to the Kubernetes API, not to AWS. kubectl uses the AWS identity
     (through the IAM authenticator) to prove who it is, and the cluster's access entry decides what it
     may do.

So the chain is: AWS credentials on the agent -> AWS CLI (STS, ECR, EKS) -> kubectl to the EKS API.

### How the agent authenticates to AWS (pick one)

| Method | How | Good / bad |
|--------|-----|-----------|
| **Instance profile (IAM role on the EC2 agent)** | Attach an IAM role to the agent EC2. The CLI reads temporary credentials from instance metadata. No keys stored | Best for an EC2 agent: no static keys, auto-rotated. Recommended |
| **Jenkins AWS credentials** | Store an access key in Jenkins (Credentials -> AWS), inject per job | Works, but it is a long-lived key to guard and rotate. The `DEPLOYMENT-GUIDE.md` step 7d sets this up (`aws-credentials`) |
| **Static keys in env** | `aws configure` on the agent | Avoid. Keys sit on disk |

This project's `DEPLOYMENT-GUIDE.md` uses the Jenkins AWS credentials method (step 7d). The stronger
option is to give the agent EC2 an **instance profile** with a least-privilege policy and store no keys
at all. Either way, the identity needs:

- ECR: `ecr:GetAuthorizationToken`, `ecr:DescribeRepositories`, `ecr:CreateRepository`,
  and push/pull on the repos (`BatchCheckLayerAvailability`, `PutImage`, `InitiateLayerUpload`,
  `UploadLayerPart`, `CompleteLayerUpload`).
- EKS: `eks:DescribeCluster` (for `update-kubeconfig`), plus an **EKS access entry** (or an aws-auth
  mapping) that grants the agent's IAM identity rights inside the cluster. Without the access entry,
  `aws eks update-kubeconfig` works but `kubectl` is denied by the cluster.

### Two identity layers for EKS (the part people miss)

Reaching the cluster needs two separate grants:

1. **AWS IAM** lets the agent call `eks:DescribeCluster` and build the kubeconfig.
2. **Kubernetes RBAC via an EKS access entry** lets that same IAM identity actually run `kubectl`
   commands. In this project the Terraform uses `enable_cluster_creator_admin_permissions`, so the
   creator identity is admin. A different agent identity needs its own access entry.

If `kubectl` returns `error: You must be logged in to the server (Unauthorized)`, layer 1 worked and
layer 2 is missing: add an EKS access entry for the agent's IAM role.

### Where this sits in the big flow

This is inside **Phase 3 and Phase 4** of the picture at the top. The "Jenkins CI" to "Docker" to ECR
arrows are the ECR calls here. In the current Jenkinsfile the "Deploy to EKS" stage also calls EKS and
runs `kubectl` directly. The GitOps design moves deployment to ArgoCD, so in the GitOps version Jenkins
only needs ECR access, and ArgoCD (inside the cluster) does the deploy, so Jenkins no longer needs EKS
access at all.
