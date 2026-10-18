# Project 1 (hybrid model router): one target per workshop stage.
# Run from this folder (01-hybrid-model-router), in order. Each terraform target shows its plan and
# asks for "yes" before changing anything.
#   make check network ecr image gateway eks addons storage model gpu vllm
# Teardown: make destroy

TF_DIR   := terraform/envs/dev
K8S_DIR  := k8s
TFVARS   := $(TF_DIR)/terraform.tfvars

# Values read from terraform.tfvars, so there is one place to change them.
tfvar     = $(shell sed -n 's/^$(1)[[:space:]]*=[[:space:]]*"\(.*\)"/\1/p' $(TFVARS))
REGION    := $(call tfvar,region)
NAME      := $(call tfvar,name)
IMAGE_TAG := $(call tfvar,gateway_image_tag)

# Helm pulls OCI charts through Docker's credential helper (docker-credential-desktop).
DOCKER_BIN := /Applications/Docker.app/Contents/Resources/bin
export PATH := $(DOCKER_BIN):$(PATH)
# Make 3.81 (macOS) finds simple commands on the original PATH, so name docker
# by full path when Docker Desktop's CLI isn't installed on PATH.
DOCKER := $(shell command -v docker 2>/dev/null || echo $(DOCKER_BIN)/docker)

TF := terraform -chdir=$(TF_DIR)

VPC_CIDR  := $(call tfvar,vpc_cidr)

.PHONY: check init network ecr image gateway eks addons kubeconfig storage model gpu vllm vllm-url destroy

check: ## Tools installed, AWS identity, Docker running
	@for t in aws terraform kubectl helm envsubst $(DOCKER); do \
	  command -v $$t >/dev/null || { echo "missing: $$t"; exit 1; }; done
	@$(DOCKER) info >/dev/null 2>&1 || { echo "Docker is not running"; exit 1; }
	@echo "AWS identity: $$(aws sts get-caller-identity --query Arn --output text)"
	@echo "Region: $(REGION)  Name: $(NAME)  Gateway image: $(IMAGE_TAG)"

init:
	$(TF) init -input=false -backend-config=backend.hcl

network: init ## 01: VPC, subnets, NAT, CloudShell security group
	$(TF) apply -target=module.networking

ecr: init ## 02a: the gateway's ECR repository only
	$(TF) apply -target=module.gateway.module.ecr

image: ## 02b: build the router image and push it to ECR
	$(eval REPO := $(shell $(TF) output -raw gateway_ecr_repository_url))
	aws ecr get-login-password --region $(REGION) | $(DOCKER) login --username AWS --password-stdin $(firstword $(subst /, ,$(REPO)))
	$(DOCKER) build --platform linux/amd64 -t $(REPO):$(IMAGE_TAG) app
	$(DOCKER) push $(REPO):$(IMAGE_TAG)

gateway: init ## 02c: ALB, ECS cluster and service, master key
	$(TF) apply -target=module.gateway

eks: init ## 03: EKS cluster, system nodes, add-ons, access entries
	$(TF) apply -target=module.gpu_compute.module.eks

addons: init ## 04-05: everything else (EFS, Karpenter, KEDA, Prometheus)
	$(TF) apply

kubeconfig:
	aws eks update-kubeconfig --region $(REGION) --name $(NAME)

storage: kubeconfig ## 04: vllm namespace, EFS StorageClass and PVC
	kubectl apply -f $(K8S_DIR)/namespace.yaml
	EFS_FILE_SYSTEM_ID=$$($(TF) output -raw efs_file_system_id) envsubst < $(K8S_DIR)/model-storage.yaml | kubectl apply -f -

model: kubeconfig ## 04: download the model weights onto EFS
	kubectl apply -f $(K8S_DIR)/model-download-job.yaml
	kubectl wait -n vllm --for=condition=complete job/model-download --timeout=900s
	kubectl logs -n vllm job/model-download --tail=15

gpu: kubeconfig ## 06: spot GPU NodePool for Karpenter (no node launches until a GPU pod is pending)
	CLUSTER_NAME=$(NAME) KARPENTER_NODE_ROLE=$$($(TF) output -raw karpenter_node_iam_role_name) \
	  envsubst < $(K8S_DIR)/gpu-nodepool.yaml | kubectl apply -f -

vllm: kubeconfig ## 06: vLLM Deployment, its internal NLB, and the KEDA ScaledObject
	VPC_CIDR=$(VPC_CIDR) envsubst < $(K8S_DIR)/vllm-service.yaml | kubectl apply -f -
	kubectl apply -f $(K8S_DIR)/vllm-deployment.yaml
	kubectl apply -f $(K8S_DIR)/keda-scaledobject.yaml

vllm-url: ## 06: the NLB address to put in terraform.tfvars
	@echo "http://$$(kubectl get svc -n vllm vllm -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'):8000"

destroy: ## 08: remove everything, in the right order
	scripts/teardown.sh
