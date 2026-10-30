# DevOps Microservices Platform — Jenkins CI/CD to EKS

Three Flask microservices (`order-service`, `payment-service`,
`user-service`) built and deployed to an Amazon EKS cluster via a
**Jenkins** pipeline (`Jenkinsfile`), with infrastructure managed by
Terraform. Jenkins, ArgoCD, monitoring, and SonarQube run as in-cluster
workloads (see `kubernetes/`).

> **Known gap, read before running a first deploy:** the Jenkinsfile's
> "Deploy to EKS" stage looks for manifests at `kubernetes/<service-name>/`
> or `kubernetes/<service-name>.yaml` — neither exists yet (only
> `kubernetes/argocd`, `ingress`, `jenkins`, `monitoring`, `namespaces`,
> `sonarqube` do). The real Helm chart lives at `charts/microservice/` but
> the Jenkinsfile never calls `helm` at all. On a fresh service, the
> pipeline will build and push the image successfully, then the deploy
> stage will just print "No Kubernetes manifests found" and stop — nothing
> gets deployed. Until this is wired up (either add the Jenkinsfile calling
> `helm upgrade --install`, or add real manifests under `kubernetes/<service>/`),
> **you must deploy each service's first release manually via Helm** (step
> 6 below) — after that, the Jenkinsfile's `kubectl set image` step can
> update the image on an *existing* deployment, since that path doesn't
> depend on the missing manifests.

---

## What's in this repo

```
devops-microservices-platform/
├── app/
│   ├── order-service/      # Flask app — Dockerfile + requirements.txt
│   ├── payment-service/
│   └── user-service/
├── charts/microservice/    # Helm chart — NOT currently called by Jenkinsfile
├── kubernetes/
│   ├── argocd/, ingress/, jenkins/, monitoring/, namespaces/, sonarqube/
│   └── (no per-service manifests yet — see gap above)
├── Terraform/
│   ├── vpc.tf, eks.tf, iam-*.tf, ecr.tf, eks-addons.tf, ...
│   └── tfvars/{dev,prod}/
├── Jenkinsfile             # parameterized: pick a service, build, push, deploy
└── scripts/
```

## End-to-end: running this project from zero

### 0. Prerequisites

- AWS account + credentials, `terraform` >= 1.3, `kubectl`, `helm`, `aws` CLI
- A Jenkins controller with an agent labeled `AGENT` (the Jenkinsfile pins
  `agent { label 'AGENT' }`), Docker available on that agent, and the `aws`
  CLI configured with credentials that can push to ECR / reach EKS
- The S3 backend bucket + lock table referenced in
  `Terraform/tfvars/dev/backend.tfvars` must already exist (Terraform's S3
  backend does not create them)

### 1. Provision AWS infrastructure (Terraform)

```bash
cd Terraform
terraform init -backend-config=tfvars/dev/backend.tfvars
terraform plan -var-file=tfvars/dev/dev.tfvars
terraform apply -var-file=tfvars/dev/dev.tfvars
```

This creates the VPC, the EKS cluster (`expense-dev` by default), a managed
node group, ECR repos, and IAM roles (node group + IRSA for EBS CSI / ALB controller — see `iam-irsa.tf`).

```bash
terraform output
```

### 2. Point kubectl at the cluster

```bash
aws eks update-kubeconfig --name expense-dev --region us-east-1
kubectl get nodes
```

### 3. Install cluster add-ons

Terraform creates the IRSA *roles*; the controllers themselves are
installed via Helm/manifests, not Terraform:

```bash
# AWS Load Balancer Controller (required for any Ingress in charts/microservice)
helm repo add eks https://aws.github.io/eks-charts
helm repo update
cat > alb-controller-values.yaml <<'YAML'
clusterName: expense-dev
serviceAccount:
  create: true
  annotations:
    eks.amazonaws.com/role-arn: "PASTE_terraform_output_alb_controller_role_arn_HERE"
YAML
helm install aws-load-balancer-controller eks/aws-load-balancer-controller \
  -n kube-system -f alb-controller-values.yaml
```
(Fill in the real role ARN from `terraform output` before running — don't
leave the placeholder in, and don't put the file together with a shell
heredoc if you're on Windows Git Bash/PowerShell, since heredocs there can
inject stray characters into the YAML; write the file directly instead.)

```bash
# Jenkins, ArgoCD, monitoring, SonarQube — manifests already in this repo
kubectl apply -f kubernetes/namespaces/
kubectl apply -f kubernetes/jenkins/
kubectl apply -f kubernetes/argocd/
kubectl apply -f kubernetes/monitoring/
kubectl apply -f kubernetes/sonarqube/
kubectl apply -f kubernetes/ingress/
```

### 4. Set up Jenkins

Once the `kubernetes/jenkins/` manifests are applied, get the initial admin
password and access Jenkins (via the Ingress, or port-forward if the ALB
isn't wired up yet):
```bash
kubectl get pods -n jenkins
kubectl exec -n jenkins <jenkins-pod> -- cat /var/jenkins_home/secrets/initialAdminPassword
```
Create a Pipeline job pointing at this repo's `Jenkinsfile`, and make sure
at least one agent is labeled `AGENT` (Manage Jenkins → Nodes) with Docker
and the AWS CLI available — the pipeline's `agent { label 'AGENT' }` and
every `sh` step depend on both.

### 5. Run the pipeline

Build with Parameters → pick `SERVICE_NAME` (`order-service` /
`payment-service` / `user-service`) and an `IMAGE_TAG`. The pipeline will:
1. Check out this repo
2. Build + "test" the selected service (currently placeholder echo steps —
   see `Build & Test` stage; add real test commands per service as they exist)
3. `docker build` + push to ECR (creates the ECR repo if it doesn't exist yet)
4. Attempt to deploy — **this is where the known gap above applies**: on a
   brand-new service this stage currently has no manifests to apply

### 6. Deploy the first release manually via Helm

Since the Jenkinsfile can't yet deploy a service that has no existing
Kubernetes objects, install each service once via Helm directly:

```bash
helm install order-service charts/microservice \
  -f charts/microservice/values.yaml \
  -f charts/microservice/values-order.yaml \
  -n default

helm install payment-service charts/microservice \
  -f charts/microservice/values.yaml \
  -f charts/microservice/values-payment.yaml \
  -n default

helm install user-service charts/microservice \
  -f charts/microservice/values.yaml \
  -f charts/microservice/values-user.yaml \
  -n default
```

After this, the Jenkinsfile's `kubectl set image deployment/${SERVICE_NAME} ...`
step will work on subsequent runs, since it only needs the Deployment to
already exist — it doesn't create one from scratch.

### 7. Confirm it's running

```bash
kubectl get pods
kubectl get ingress
```

### 8. Teardown (avoid ongoing cost)

```bash
helm uninstall order-service payment-service user-service
kubectl delete -f kubernetes/sonarqube/ -f kubernetes/monitoring/ -f kubernetes/argocd/ -f kubernetes/jenkins/
cd Terraform
terraform destroy -var-file=tfvars/dev/dev.tfvars
```
Remove the Helm releases and any Ingress-backed workloads before
`terraform destroy` — otherwise orphaned ALBs can be left behind in AWS
after the cluster is gone.

## Closing the Jenkinsfile/Helm gap (next real improvement)

The cleanest fix is to replace the Jenkinsfile's "Deploy to EKS" `kubectl`
block with a Helm upgrade/install that always works, first deploy or not:

```groovy
sh '''
    helm upgrade --install ${SERVICE_NAME} charts/microservice \
      -f charts/microservice/values.yaml \
      -f charts/microservice/values-${SERVICE_NAME#*-}.yaml \
      --set image.tag=${IMAGE_TAG} \
      -n default
'''
```
(Adjust the `values-*.yaml` naming to match exactly — `values-order.yaml`,
not `values-order-service.yaml`, per what's actually in `charts/microservice/`.)
This removes the manifest-detection logic entirely and makes every run —
first deploy or update — go through the same, always-correct path.
