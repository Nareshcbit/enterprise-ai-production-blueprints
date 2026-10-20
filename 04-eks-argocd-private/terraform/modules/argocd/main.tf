# The managed Argo CD (EKS Capability for Argo CD): its IAM role, the
# capability itself, and Argo CD's write access to the hub cluster.
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
  description = "Name prefix for the capability and its IAM role."
  type        = string
}

variable "cluster_name" {
  description = "EKS cluster that hosts the capability."
  type        = string
}

variable "vpce_id" {
  description = "eks-capabilities interface endpoint ID. Setting it blocks public access to Argo CD."
  type        = string
}

variable "idc_instance_arn" {
  description = "IAM Identity Center instance ARN (from `aws sso-admin list-instances`)."
  type        = string
}

variable "idc_region" {
  description = "Region of the Identity Center instance."
  type        = string
}

variable "admin_identity" {
  description = "Identity Center user or group mapped to the Argo CD ADMIN role."
  type = object({
    id   = string
    type = string
  })

  validation {
    condition     = contains(["SSO_USER", "SSO_GROUP"], var.admin_identity.type)
    error_message = "type must be SSO_USER or SSO_GROUP."
  }
}

variable "deploy_namespace" {
  description = "Namespace on the hub where Argo CD may create and change resources."
  type        = string
}

################################################################################
# Capability IAM role
# No permission policies: public Git needs none. Add CodeConnections,
# CodeCommit or Secrets Manager permissions here when you use them.
################################################################################

resource "aws_iam_role" "capability" {
  name = "${var.name}-argocd-capability"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "capabilities.eks.amazonaws.com" }
      Action    = ["sts:AssumeRole", "sts:TagSession"]
    }]
  })
}

################################################################################
# Argo CD capability
################################################################################

resource "aws_eks_capability" "argocd" {
  cluster_name              = var.cluster_name
  capability_name           = "argocd"
  type                      = "ARGOCD"
  role_arn                  = aws_iam_role.capability.arn
  delete_propagation_policy = "RETAIN" # the only value AWS accepts

  configuration {
    argo_cd {
      namespace = "argocd"

      aws_idc {
        idc_instance_arn = var.idc_instance_arn
        idc_region       = var.idc_region
      }

      rbac_role_mapping {
        role = "ADMIN"
        identity {
          id   = var.admin_identity.id
          type = var.admin_identity.type
        }
      }

      network_access {
        vpce_ids = [var.vpce_id]
      }
    }
  }
}

################################################################################
# Argo CD's access to the hub cluster
# EKS creates the capability role's access entry, with no permissions. Argo CD
# needs to read every resource type cluster-wide (health checks, drift), and to
# write only where it deploys.
################################################################################

resource "aws_eks_access_policy_association" "read" {
  cluster_name  = var.cluster_name
  principal_arn = aws_iam_role.capability.arn
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSAdminViewPolicy"

  access_scope {
    type = "cluster"
  }

  depends_on = [aws_eks_capability.argocd]
}

resource "aws_eks_access_policy_association" "deploy" {
  cluster_name  = var.cluster_name
  principal_arn = aws_iam_role.capability.arn
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSEditPolicy"

  access_scope {
    type       = "namespace"
    namespaces = [var.deploy_namespace]
  }

  depends_on = [aws_eks_capability.argocd]
}

################################################################################
# Outputs
################################################################################

output "server_url" {
  description = "Argo CD UI and API URL. Resolves to the VPC endpoint's private IPs."
  value       = one(one(aws_eks_capability.argocd.configuration).argo_cd).server_url
}

output "capability_role_arn" {
  description = "Capability IAM role ARN (the principal in every target cluster's access entry)."
  value       = aws_iam_role.capability.arn
}
