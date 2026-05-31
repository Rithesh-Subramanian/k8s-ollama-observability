#!/usr/bin/env bash
# Load Grafana dashboard JSON from grafana/dashboards/ into the monitoring namespace.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAMESPACE="${GRAFANA_NAMESPACE:-monitoring}"

kubectl create configmap grafana-dashboards \
  -n "${NAMESPACE}" \
  --from-file="${ROOT}/grafana/dashboards/llm-inference.json" \
  --from-file="${ROOT}/grafana/dashboards/overview.json" \
  --from-file="${ROOT}/grafana/dashboards/nvidia-gpu.json" \
  --from-file="${ROOT}/grafana/dashboards/k8s-cluster.json" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl rollout restart deployment/grafana -n "${NAMESPACE}"
echo "Grafana dashboards synced and deployment restarted."
