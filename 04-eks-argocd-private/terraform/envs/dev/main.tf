# Dev environment entrypoint: VPC with the eks-capabilities endpoint, the EKS
# hub cluster, the private Argo CD capability, and an SSM-only access host.

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.28"
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

module "network" {
  source = "../../modules/network"

  name            = var.name
  cidr            = var.vpc_cidr
  azs             = var.azs
  public_subnets  = var.public_subnets
  private_subnets = var.private_subnets
}

module "cluster" {
  source = "../../modules/cluster"

  name                = var.name
  kubernetes_version  = var.kubernetes_version
  vpc_id              = module.network.vpc_id
  private_subnet_ids  = module.network.private_subnet_ids
  public_access_cidrs = var.public_access_cidrs
  access_entries      = var.eks_access_entries
}

module "argocd" {
  source = "../../modules/argocd"

  name             = var.name
  cluster_name     = module.cluster.cluster_name
  vpce_id          = module.network.eks_capabilities_vpce_id
  idc_instance_arn = var.idc_instance_arn
  idc_region       = var.idc_region
  admin_identity   = var.argocd_admin_identity
  deploy_namespace = var.deploy_namespace
}

module "access_host" {
  source = "../../modules/access_host"

  name      = var.name
  vpc_id    = module.network.vpc_id
  subnet_id = module.network.private_subnet_ids[0]
}
