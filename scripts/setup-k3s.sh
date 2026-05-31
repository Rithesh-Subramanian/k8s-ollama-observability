#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${YELLOW}Setting up k3s cluster...${NC}"

# Check if k3s is already installed
if command -v k3s &> /dev/null; then
    echo -e "${GREEN}k3s is already installed.${NC}"
    exit 0
fi

# Install k3s without traefik (we don't need an ingress controller for this lab)
# We configure k3s to use docker so it seamlessly integrates with the NVIDIA Container Toolkit
echo -e "${YELLOW}Installing k3s...${NC}"
curl -sfL https://get.k3s.io | sh -s - --docker --disable traefik

echo -e "${YELLOW}Waiting for k3s node to be ready...${NC}"
# Wait for node to be ready
while true; do
    if sudo k3s kubectl get nodes | grep -q "Ready"; then
        break
    fi
    sleep 2
done

# Copy kubeconfig so local kubectl works without sudo
mkdir -p ~/.kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown $USER ~/.kube/config

echo -e "${GREEN}k3s cluster is up and running!${NC}"
kubectl get nodes
