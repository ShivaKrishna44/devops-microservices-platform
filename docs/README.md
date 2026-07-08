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