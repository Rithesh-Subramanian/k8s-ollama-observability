#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m'

check_status() {
    local cmd=$1
    local name=$2
    if eval "$cmd" > /dev/null 2>&1; then
        echo -e "${GREEN}[OK]${NC} $name"
    else
        echo -e "${RED}[FAIL]${NC} $name"
    fi
}

echo -e "${YELLOW}Validating LLM Observability Stack...${NC}\n"

# Check Pods
echo "--- Pod Status ---"
kubectl get pods -n monitoring | grep -v "Running\|Completed" || echo -e "${GREEN}All monitoring pods Running${NC}"
kubectl get pods -n llm | grep -v "Running\|Completed" || echo -e "${GREEN}All LLM pods Running${NC}"
echo ""

# We assume port-forward is running for these checks
echo "--- Service Health (requires 'make port-forward' running in another terminal) ---"
if curl -s http://localhost:9090/-/healthy > /dev/null; then
    echo -e "${GREEN}[OK]${NC} Prometheus API"
else
    echo -e "${RED}[FAIL]${NC} Prometheus API (Is port-forward running?)"
fi

if curl -s http://localhost:3000/api/health > /dev/null; then
    echo -e "${GREEN}[OK]${NC} Grafana API"
else
    echo -e "${RED}[FAIL]${NC} Grafana API (Is port-forward running?)"
fi

echo -e "\n${GREEN}Validation complete.${NC}"
