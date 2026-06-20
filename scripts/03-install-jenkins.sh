#!/bin/bash
set -euo pipefail

echo "========================================="
echo "Installing Jenkins"
echo "========================================="

./kubectl.exe create namespace jenkins \
  --dry-run=client -o yaml | ./kubectl.exe apply -f -

./helm.exe repo add jenkins https://charts.jenkins.io
./helm.exe repo update

# FIX: Corrected line breaks and updated file path pointing into Terraform/
./helm.exe upgrade --install jenkins \
  jenkins/jenkins \
  -n jenkins \
  -f Terraform/jenkins-values.yaml

echo "========================================="
echo "Jenkins Pods"
echo "========================================="
./kubectl.exe get pods -n jenkins

echo "========================================="
echo "Jenkins Service"
echo "========================================="
./kubectl.exe get svc -n jenkins
