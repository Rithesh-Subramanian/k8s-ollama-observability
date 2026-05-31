#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${YELLOW}Tearing down observability stack...${NC}"

# Delete all resources by label to avoid deleting default k3s components
kubectl delete all,configmaps,secrets,daemonsets,clusterroles,clusterrolebindings,serviceaccounts,persistentvolumeclaims -l part-of=llm-observability-stack -n monitoring --ignore-not-found
kubectl delete all,configmaps,secrets,daemonsets,clusterroles,clusterrolebindings,serviceaccounts,persistentvolumeclaims -l part-of=llm-observability-stack -n llm --ignore-not-found

echo -e "${YELLOW}Do you want to completely uninstall k3s? (y/N)${NC}"
read -r response
if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
    echo -e "${YELLOW}Uninstalling k3s...${NC}"
    if command -v k3s-uninstall.sh &> /dev/null; then
        /usr/local/bin/k3s-uninstall.sh
    else
        echo -e "${RED}k3s-uninstall.sh not found.${NC}"
    fi
fi

echo -e "${GREEN}Teardown complete!${NC}"
