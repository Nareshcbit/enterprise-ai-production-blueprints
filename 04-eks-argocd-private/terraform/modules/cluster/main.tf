# EKS cluster that hosts the Argo CD capability (the hub) and the sample app.
# Thin wrapper over terraform-aws-modules/eks/aws.
# Tags come from the caller's provider default_tags.

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.28"
    }
  }
}

################################################################################
# Inputs
################################################################################

variable "name" {
  description = "EKS cluster name."
  type        = string
}

variable "kubernetes_version" {
  description = "Kubernetes version of the control plane, e.g. 1.37."
  type        = string
}

variable "vpc_id" {
  description = "VPC to run the cluster in."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnets for the control plane ENIs and the nodes."
  type        = list(string)
}

variable "public_access_cidrs" {
  description = "CIDRs allowed to reach the public Kubernetes API (your workstation's IPv4 /32). Never 0.0.0.0/0."
  type        = list(string)
  default     = []

  validation {
    condition     = length(var.public_access_cidrs) > 0 && !contains(var.public_access_cidrs, "0.0.0.0/0")
    error_message = "List at least one CIDR, and never 0.0.0.0/0."
  }
}

variable "access_entries" {
  description = "IAM principals allowed into the cluster, keyed by a short name. access is admin (cluster-admin) or view (read-only)."
  type = map(object({
    principal_arn = string
    access        = string
  }))
  default = {}

  validation {
    condition     = alltrue([for e in values(var.access_entries) : contains(["admin", "view"], e.access)])
    error_message = "access must be admin or view."
  }
}

variable "node_instance_types" {
  description = "Instance types for the managed node group."
  type        = list(string)
  default     = ["t3.medium"]
}

variable "node_count" {
  description = "Number of nodes (fixed size)."
  type        = number
  default     = 2
}

################################################################################
# EKS cluster
################################################################################

locals {
  access_policies = {
    admin = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
    view  = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSViewPolicy"
  }

  access_entries = {
    for key, entry in var.access_entries : key => {
      principal_arn = entry.principal_arn
      policy_associations = {
        (entry.access) = {
          policy_arn   = local.access_policies[entry.access]
          access_scope = { type = "cluster" }
        }
      }
    }
  }
}

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 21.29"

  name               = var.name
  kubernetes_version = var.kubernetes_version

  vpc_id     = var.vpc_id
  subnet_ids = var.private_subnet_ids

  # Nodes use the private endpoint. The public endpoint is only for kubectl
  # from your workstation, limited to public_access_cidrs.
  endpoint_private_access      = true
  endpoint_public_access       = true
  endpoint_public_access_cidrs = var.public_access_cidrs

  # Access is listed explicitly, so it doesn't depend on who runs terraform apply.
  enable_cluster_creator_admin_permissions = false
  access_entries                           = local.access_entries

  addons = {
    vpc-cni = {
      before_compute = true
    }
    eks-pod-identity-agent = {
      before_compute = true
    }
    kube-proxy = {}
    coredns    = {}
  }

  eks_managed_node_groups = {
    default = {
      instance_types = var.node_instance_types
      capacity_type  = "ON_DEMAND"

      min_size     = var.node_count
      max_size     = var.node_count
      desired_size = var.node_count
    }
  }
}

################################################################################
# Outputs
################################################################################

output "cluster_name" {
  description = "EKS cluster name."
  value       = module.eks.cluster_name
}

output "cluster_arn" {
  description = "EKS cluster ARN (Argo CD registers clusters by ARN)."
  value       = module.eks.cluster_arn
}
