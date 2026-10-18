# Dev environment entrypoint: wires the networking, gateway and GPU compute modules.

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.28"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 3.3"
    }
  }

  # Bucket, key and region come from backend.hcl (gitignored; copy
  # backend.hcl.example): terraform init -backend-config=backend.hcl
  backend "s3" {
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = var.tags
  }
}

# Installs charts into the EKS cluster; authenticates with a short-lived token.
provider "helm" {
  kubernetes = {
    host                   = module.gpu_compute.cluster_endpoint
    cluster_ca_certificate = base64decode(module.gpu_compute.cluster_certificate_authority_data)
    exec = {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args        = ["eks", "get-token", "--cluster-name", module.gpu_compute.cluster_name, "--region", var.region]
    }
  }
}

module "networking" {
  source = "../../modules/networking"

  name               = var.name
  cidr               = var.vpc_cidr
  azs                = var.azs
  public_subnets     = var.public_subnets
  private_subnets    = var.private_subnets
  single_nat_gateway = var.single_nat_gateway

  enable_vpc_endpoints = var.enable_vpc_endpoints
}

module "gateway" {
  source = "../../modules/gateway_fargate"

  name               = "${var.name}-gateway"
  vpc_id             = module.networking.vpc_id
  vpc_cidr_block     = module.networking.vpc_cidr_block
  private_subnet_ids = module.networking.private_subnet_ids

  image_tag                    = var.gateway_image_tag
  bedrock_inference_profile_id = var.bedrock_inference_profile_id
  vllm_api_base                = var.vllm_api_base
  vllm_metrics_url             = var.vllm_metrics_url
  router_cache_mode            = var.router_cache_mode
}

module "gpu_compute" {
  source = "../../modules/gpu_compute"

  name               = var.name
  kubernetes_version = var.kubernetes_version
  access_entries     = var.eks_access_entries
  karpenter_version  = var.karpenter_version
  keda_version       = var.keda_version
  prometheus_version = var.prometheus_version

  lb_controller_version = var.lb_controller_version
  vpc_id                = module.networking.vpc_id
  private_subnet_ids    = module.networking.private_subnet_ids
}
