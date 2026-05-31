#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${YELLOW}Applying Kubernetes manifests...${NC}"

# Apply namespaces first
kubectl apply -f kubernetes/namespaces.yaml

# Apply NVIDIA dependencies (Device Plugin + DCGM)
echo -e "${YELLOW}Deploying NVIDIA components...${NC}"
kubectl apply -f kubernetes/nvidia/

# Apply Prometheus
echo -e "${YELLOW}Deploying Prometheus...${NC}"
kubectl apply -f kubernetes/prometheus/
kubectl apply -f kubernetes/prometheus/rules/

# Apply kube-state-metrics and node-exporter
echo -e "${YELLOW}Deploying Node & Cluster Exporters...${NC}"
kubectl apply -f kubernetes/kube-state-metrics/
kubectl apply -f kubernetes/node-exporter/

# Apply Grafana
echo -e "${YELLOW}Deploying Grafana...${NC}"
kubectl apply -f kubernetes/grafana/
bash "$(dirname "$0")/sync-grafana-dashboards.sh"

# Apply Ollama
echo -e "${YELLOW}Deploying Ollama Inference Engine...${NC}"
kubectl apply -f kubernetes/ollama/

# Apply Ollama Exporter
echo -e "${YELLOW}Deploying Custom Ollama Exporter...${NC}"
kubectl apply -f kubernetes/ollama-exporter/

echo -e "${YELLOW}Waiting for pods to be ready (this may take a minute)...${NC}"
kubectl wait --for=condition=ready pod -l app=prometheus -n monitoring --timeout=120s || true
kubectl wait --for=condition=ready pod -l app=grafana -n monitoring --timeout=120s || true
kubectl wait --for=condition=ready pod -l app=ollama -n llm --timeout=300s || true

echo -e "${GREEN}Deployment applied successfully!${NC}"
