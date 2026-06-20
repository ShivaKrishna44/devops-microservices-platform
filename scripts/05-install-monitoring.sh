#!/bin/bash
set -euo pipefail

./helm.exe repo add prometheus-community \
https://prometheus-community.github.io/helm-charts

./helm.exe repo update

./kubectl.exe create namespace monitoring \
--dry-run=client -o yaml | ./kubectl.exe apply -f -

./helm.exe install monitoring \
prometheus-community/kube-prometheus-stack \
-n monitoring

./kubectl.exe get pods -n monitoring

echo " ✔ Prometheus ✔ Grafana ✔ Alertmanager "