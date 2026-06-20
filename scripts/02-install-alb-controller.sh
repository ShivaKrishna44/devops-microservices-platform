#!/bin/bash
set -euo pipefail

CLUSTER_NAME="expense-dev"

echo "========================================="
echo "Installing AWS Load Balancer Controller"
echo "========================================="

./helm.exe repo add eks https://aws.github.io/eks-charts

./helm.exe repo update

./helm.exe upgrade --install aws-load-balancer-controller 
eks/aws-load-balancer-controller 
-n kube-system 
--set clusterName=$CLUSTER_NAME 
--set serviceAccount.create=true 
--set serviceAccount.name=aws-load-balancer-controller

echo "Waiting for controller..."

sleep 20

./kubectl.exe get pods 
-n kube-system 
-l app.kubernetes.io/name=aws-load-balancer-controller

echo " ###### AWS Load Balancer Controller and  ALB Ingress Support done ###### "