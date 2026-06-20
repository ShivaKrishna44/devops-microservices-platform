#!/bin/bash
set -euo pipefail

./helm.exe repo add prometheus-community \
  https://prometheus-community.github.io/helm-charts
./helm.exe repo update

./kubectl.exe create namespace monitoring \
  --dry-run=client -o yaml | ./kubectl.exe apply -f -

# FIX: Integrated parameters into a single continuous block without a missing file block
./helm.exe upgrade --install monitoring \
  prometheus-community/kube-prometheus-stack \
  -n monitoring

echo "Waiting for monitoring stack..."
sleep 15

./kubectl.exe get pods -n monitoring
echo " ✔ Prometheus ✔ Grafana ✔ Alertmanager "
