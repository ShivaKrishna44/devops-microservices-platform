#!/bin/bash
set -euxo pipefail

echo "========================================="
echo "Jenkins Agent Setup"
echo "========================================="

REGISTRY_REGION="us-east-1"
EKS_CLUSTER="expense-dev"

echo
echo "========================================="
echo "1. Installing Java 21"
echo "========================================="

# FIX: java-21-amazon-corretto is not available on RHEL 9 via default repos
# Use java-21-openjdk which is in the standard RHEL/EPEL repos
sudo dnf install -y java-21-openjdk java-21-openjdk-devel

java -version

echo
echo "========================================="
echo "2. Installing Git"
echo "========================================="

sudo dnf install -y git

git --version

echo
echo "========================================="
echo "3. Installing kubectl"
echo "========================================="

# FIX: Added -f flag so HTTP errors fail the script
# FIX: Added curl for the stable version lookup too
KUBECTL_VERSION=$(curl -fsSL https://dl.k8s.io/release/stable.txt)
curl -fLO "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl"

chmod +x kubectl
sudo mv kubectl /usr/local/bin/

kubectl version --client

echo
echo "========================================="
echo "4. Installing Terraform"
echo "========================================="

sudo dnf install -y yum-utils

# FIX: Fixed broken multi-line commands — added proper \ line continuations
sudo yum-config-manager \
  --add-repo \
  https://rpm.releases.hashicorp.com/RHEL/hashicorp.repo

sudo dnf install -y terraform

terraform version

echo
echo "========================================="
echo "5. Installing Docker"
echo "========================================="

# FIX: Fixed broken multi-line commands
sudo dnf config-manager \
  --add-repo \
  https://download.docker.com/linux/rhel/docker-ce.repo

sudo dnf install -y \
  docker-ce \
  docker-ce-cli \
  containerd.io

sudo systemctl enable docker
sudo systemctl start docker

# FIX: Added jenkins user to docker group if it exists
sudo usermod -aG docker ec2-user
id jenkins &>/dev/null && sudo usermod -aG docker jenkins || true

docker --version

echo
echo "========================================="
echo "6. Configure EKS Access"
echo "========================================="

# FIX: Fixed broken multi-line command
aws eks update-kubeconfig \
  --region ${REGISTRY_REGION} \
  --name ${EKS_CLUSTER}

kubectl get nodes

echo
echo "========================================="
echo "7. Create Jenkins Directories"
echo "========================================="

mkdir -p ~/jenkins
chmod 755 ~/jenkins

echo
echo "========================================="
echo "8. Validate AWS Access"
echo "========================================="

aws sts get-caller-identity

echo
echo "========================================="
echo "9. Validate ECR"
echo "========================================="

aws ecr describe-repositories --region ${REGISTRY_REGION}

echo
echo "========================================="
echo "10. Validation Summary"
echo "========================================="

echo "JAVA:";      java -version
echo "AWS:";       aws --version
echo "GIT:";       git --version
echo "KUBECTL:";   kubectl version --client
echo "TERRAFORM:"; terraform version
echo "DOCKER:";    docker --version
echo "EKS:";       kubectl get nodes

echo
echo "========================================="
echo "Agent Setup Completed"
echo "========================================="
