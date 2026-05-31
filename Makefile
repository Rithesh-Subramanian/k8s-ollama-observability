# ============================================================================
# LLM Observability Stack — Makefile
# ============================================================================
# One-command automation for setting up and managing the observability stack
# on a local Kubernetes cluster (k3s) on WSL2 with NVIDIA GPUs.
# ============================================================================

.PHONY: help setup deploy teardown validate port-forward build-exporter clean pull-model test-inference test-token-metrics grafana-dashboards

# --- Colors ---
GREEN  := \033[0;32m
YELLOW := \033[0;33m
RED    := \033[0;31m
CYAN   := \033[0;36m
BOLD   := \033[1m
RESET  := \033[0m

# --- Configuration ---
EXPORTER_IMAGE  := localhost/ollama-exporter:latest
MODEL_NAME      := llama3.2:3b

# ============================================================================
# Help
# ============================================================================

help: ## Show this help message
	@echo ""
	@echo "$(BOLD)$(CYAN)🔍 LLM Observability Stack (Windows/NVIDIA)$(RESET)"
	@echo "$(CYAN)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(RESET)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(RESET) %s\n", $$1, $$2}'
	@echo ""

# ============================================================================
# Setup — Infrastructure
# ============================================================================

setup: ## Setup k3s cluster
	@echo "$(CYAN)$(BOLD)☸️  Setting up k3s cluster...$(RESET)"
	@bash scripts/setup-k3s.sh
	@echo ""
	@echo "$(GREEN)$(BOLD)✅ Infrastructure setup complete!$(RESET)"
	@echo "   Run '$(CYAN)make deploy$(RESET)' to deploy the observability stack."

# ============================================================================
# Deploy — Observability Stack
# ============================================================================

build-exporter: ## Build ollama-exporter container image
	@echo "$(CYAN)$(BOLD)🔨 Building ollama-exporter image...$(RESET)"
	docker build -t $(EXPORTER_IMAGE) -f exporters/ollama-exporter/Dockerfile exporters/ollama-exporter/
	@echo "$(GREEN)✅ Image built: $(EXPORTER_IMAGE)$(RESET)"
	@echo "Importing image into k3s..."
	docker save $(EXPORTER_IMAGE) | sudo k3s ctr images import -

deploy: build-exporter ## Deploy full observability stack to K8s
	@echo "$(CYAN)$(BOLD)🚀 Deploying observability stack...$(RESET)"
	@bash scripts/deploy-stack.sh
	@echo ""
	@echo "$(GREEN)$(BOLD)✅ Stack deployed successfully!$(RESET)"
	@echo ""
	@echo "   Run '$(CYAN)make port-forward$(RESET)' to access Grafana and Prometheus."
	@echo "   Run '$(CYAN)make pull-model$(RESET)' to download the LLM into Ollama."

# ============================================================================
# Operations
# ============================================================================

validate: ## Health check all components
	@bash scripts/validate.sh

port-forward: ## Forward Grafana (:3000) and Prometheus (:9090) ports
	@echo "$(CYAN)Starting port-forward for Grafana and Prometheus...$(RESET)"
	@echo "   Grafana:    http://localhost:3000 (admin / observability)"
	@echo "   Prometheus: http://localhost:9090"
	@echo "   Press Ctrl+C to stop"
	@kubectl port-forward -n monitoring svc/grafana 3000:3000 & \
	 kubectl port-forward -n monitoring svc/prometheus 9090:9090 & \
	 wait

pull-model: ## Pull the default model into Ollama
	@echo "$(CYAN)$(BOLD)📥 Pulling $(MODEL_NAME) model...$(RESET)"
	kubectl exec -n llm deploy/ollama -- ollama pull $(MODEL_NAME)
	@echo "$(GREEN)✅ Model pulled successfully$(RESET)"

test-inference: ## Run a test inference against Ollama (direct — no token metrics)
	@echo "$(CYAN)Testing inference...$(RESET)"
	kubectl exec -n llm deploy/ollama -- ollama run $(MODEL_NAME) "Explain Kubernetes in one sentence." --nowordwrap

test-token-metrics: ## Generate via exporter proxy (populates token panels in Grafana)
	@echo "$(CYAN)Sending instrumented request through ollama-exporter proxy...$(RESET)"
	@kubectl run curl-token-test --rm -i --restart=Never -n llm --image=curlimages/curl:latest -- \
		curl -s http://ollama-exporter.llm.svc.cluster.local:11435/api/generate -d \
		"{\"model\":\"$(MODEL_NAME)\",\"prompt\":\"Say hello in one sentence.\",\"stream\":false}" \
		| head -c 500
	@echo ""
	@echo "$(GREEN)Check Grafana → LLM Inference — Ollama in ~30s$(RESET)"

grafana-dashboards: ## Sync grafana/dashboards/*.json into Grafana ConfigMap
	@bash scripts/sync-grafana-dashboards.sh

# ============================================================================
# Teardown
# ============================================================================

teardown: ## Clean teardown of cluster
	@echo "$(RED)$(BOLD)🗑️  Tearing down...$(RESET)"
	@bash scripts/teardown.sh
	@echo "$(GREEN)✅ Teardown complete$(RESET)"

clean: ## Remove built images and temp files
	@echo "$(CYAN)Cleaning up...$(RESET)"
	-docker rmi $(EXPORTER_IMAGE) 2>/dev/null
	-rm -rf tmp/
	@echo "$(GREEN)✅ Clean complete$(RESET)"
