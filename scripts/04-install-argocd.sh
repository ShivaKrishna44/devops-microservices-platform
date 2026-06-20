#!/bin/bash
set -euo pipefail

kubectl create namespace argocd \
--dry-run=client -o yaml | kubectl apply -f -

kubectl apply \
-n argocd \
-f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

kubectl get pods -n argocd

echo " ✔ GitOps ✔ Continuous Deployment "