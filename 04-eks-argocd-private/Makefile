# Project 4 (private Argo CD on EKS): run from this folder (04-eks-argocd-private).
#   make check test apply argocd-config verify
# Open the UI from your laptop: make ui     Teardown: make destroy
# Each terraform target shows its plan and asks for "yes" before changing anything.

TF_DIR  := terraform/envs/dev
K8S_DIR := k8s
TFVARS  := $(TF_DIR)/terraform.tfvars
MODULES := network cluster argocd access_host

# Values read from terraform.tfvars, so there is one place to change them.
tfvar  = $(shell sed -n 's/^$(1)[[:space:]]*=[[:space:]]*"\(.*\)"/\1/p' $(TFVARS))
REGION := $(call tfvar,region)
NAME   := $(call tfvar,name)

TF := terraform -chdir=$(TF_DIR)

.PHONY: check test init plan apply kubeconfig argocd-config verify ui destroy

check: ## Tools installed, AWS identity
	@for t in aws terraform kubectl envsubst dig; do \
	  command -v $$t >/dev/null || { echo "missing: $$t"; exit 1; }; done
	@command -v session-manager-plugin >/dev/null || echo "note: session-manager-plugin missing (needed only for 'make ui')"
	@echo "AWS identity: $$(aws sts get-caller-identity --query Arn --output text)"
	@echo "Region: $(REGION)  Name: $(NAME)"

test: ## Plan-only Terraform tests for every module (no AWS calls)
	@for m in $(MODULES); do \
	  echo "== $$m"; \
	  terraform -chdir=terraform/modules/$$m init -backend=false -input=false >/dev/null && \
	  terraform -chdir=terraform/modules/$$m test || exit 1; done

init:
	$(TF) init -input=false -backend-config=backend.hcl

plan: init ## Show what apply would change
	$(TF) plan

apply: init ## VPC + endpoint, EKS, Argo CD capability, access host (~20-25 min)
	$(TF) apply

kubeconfig:
	aws eks update-kubeconfig --region $(REGION) --name $(NAME)

argocd-config: kubeconfig ## Hub registration, sample project and app
	@kubectl wait --for=condition=Established crd/applications.argoproj.io --timeout=300s
	CLUSTER_ARN=$$($(TF) output -raw cluster_arn) envsubst < $(K8S_DIR)/hub-cluster.yaml | kubectl apply -f -
	CLUSTER_ARN=$$($(TF) output -raw cluster_arn) envsubst < $(K8S_DIR)/guestbook-project.yaml | kubectl apply -f -
	CLUSTER_ARN=$$($(TF) output -raw cluster_arn) envsubst < $(K8S_DIR)/guestbook-app.yaml | kubectl apply -f -

verify: ## Private DNS, blocked from outside, reachable inside, app synced
	scripts/verify.sh

ui: ## Port-forward the Argo CD UI to this laptop through the access host
	@command -v session-manager-plugin >/dev/null || { echo "install session-manager-plugin first (see README)"; exit 1; }
	$(eval HOST := $(subst https://,,$(shell $(TF) output -raw argocd_server_url)))
	@echo "One-time: add this line to /etc/hosts, then open https://$(HOST)"
	@echo "  127.0.0.1 $(HOST)"
	aws ssm start-session --region $(REGION) --target $$($(TF) output -raw access_host_id) \
	  --document-name AWS-StartPortForwardingSessionToRemoteHost \
	  --parameters host=$(HOST),portNumber=443,localPortNumber=443

destroy: ## Remove everything, in the right order
	scripts/teardown.sh
