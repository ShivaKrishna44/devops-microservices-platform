#!/bin/bash
set -euo pipefail

# FIX: Swapped out 'kubectl' for your local './kubectl.exe' runner binary
./kubectl.exe create namespace argocd \
  --dry-run=client -o yaml | ./kubectl.exe apply -f -

./kubectl.exe apply \
  -n argocd \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

echo "Waiting for core components..."
sleep 10

./kubectl.exe get pods -n argocd
echo " ✔ GitOps ✔ Continuous Deployment "
