#!/bin/bash
set -euo pipefail
source ./scripts/config.sh

./helm.exe repo add prometheus-community \
  https://prometheus-community.github.io/helm-charts
./helm.exe repo update

./kubectl.exe create namespace monitoring \
  --dry-run=client -o yaml | ./kubectl.exe apply -f -

# Create the Grafana admin secret (idempotent — skips if it already exists)
if ! ./kubectl.exe get secret grafana-admin-secret -n monitoring &>/dev/null; then
  echo "Creating grafana-admin-secret..."
  GRAFANA_PASSWORD="${GRAFANA_ADMIN_PASSWORD:-changeme}"
  echo "⚠️  Using default password 'changeme' — set GRAFANA_ADMIN_PASSWORD env var for production"
  ./kubectl.exe create secret generic grafana-admin-secret \
    --from-literal=admin-user=admin \
    --from-literal=admin-password="${GRAFANA_PASSWORD}" \
    -n monitoring
  echo "grafana-admin-secret created."
else
  echo "grafana-admin-secret already exists, skipping."
fi

# Install / upgrade kube-prometheus-stack
./helm.exe upgrade --install monitoring \
  prometheus-community/kube-prometheus-stack \
  --version 65.1.1 \
  -n monitoring \
  -f kubernetes/monitoring/grafana-values.yaml \
  --wait --timeout 10m

echo "Waiting for Grafana deployment to be ready..."
./kubectl.exe rollout status deployment/monitoring-grafana -n monitoring --timeout=300s

./kubectl.exe get pods -n monitoring
echo " ✔ Prometheus ✔ Grafana ✔ Alertmanager "

# Apply Grafana ingress for external access
echo "Applying Grafana ingress..."
./kubectl.exe apply -f kubernetes/ingress/grafana-ingress.yaml
./kubectl.exe get ingress -n monitoring
