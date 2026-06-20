#!/bin/bash
set -euo pipefail

REGION="us-east-1"
CLUSTER_NAME="expense-dev"

echo "========================================="
echo "🚀 Installing Helm"
echo "========================================="

rm -rf windows-amd64/
rm -f helm-v3.18.2-windows-amd64.zip

curl -LO https://get.helm.sh/helm-v3.18.2-windows-amd64.zip

unzip -o helm-v3.18.2-windows-amd64.zip

mv windows-amd64/helm.exe .

rm -rf windows-amd64/
rm -f helm-v3.18.2-windows-amd64.zip

echo "Helm Version:"
./helm.exe version --short

echo "========================================="
echo "Updating kubeconfig"
echo "========================================="

aws eks update-kubeconfig 
--region $REGION 
--name $CLUSTER_NAME

echo "========================================="
echo "Verifying Cluster"
echo "========================================="

./kubectl.exe get nodes


echo"  Helm install ----  kubenret config --- Cluster Validation ### "