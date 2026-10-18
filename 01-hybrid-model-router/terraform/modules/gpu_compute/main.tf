# GPU compute: EKS cluster that hosts vLLM, EFS for the model weights,
# Karpenter to launch GPU nodes on demand, KEDA + Prometheus to scale vLLM on
# its request queue, and the AWS Load Balancer Controller for vLLM's NLB.
# Thin wrapper over terraform-aws-modules/eks/aws and efs/aws. The GPU NodePool
# comes later.
# Tags come from the caller's provider default_tags.

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.28"
    }
    helm = {
      source  = "hashicorp/helm"
      version = ">= 3.3"
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

variable "karpenter_version" {
  description = "Karpenter Helm chart version; must support kubernetes_version."
  type        = string
}

variable "keda_version" {
  description = "KEDA Helm chart version."
  type        = string
}

variable "prometheus_version" {
  description = "prometheus-community/prometheus Helm chart version."
  type        = string
}

variable "lb_controller_version" {
  description = "AWS Load Balancer Controller Helm chart version."
  type        = string
}

variable "system_instance_types" {
  description = "Instance types for the system node group (CoreDNS, later Karpenter)."
  type        = list(string)
  default     = ["t3.medium"]
}

variable "system_node_count" {
  description = "Number of system nodes (fixed size)."
  type        = number
  default     = 2
}

################################################################################
# EKS cluster
################################################################################

locals {
  access_policy_arns = {
    admin = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
    view  = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSViewPolicy"
  }

  access_entries = {
    for key, entry in var.access_entries : key => {
      principal_arn = entry.principal_arn
      policy_associations = {
        (entry.access) = {
          policy_arn   = local.access_policy_arns[entry.access]
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

  # Public endpoint for kubectl from a laptop (still IAM-authenticated);
  # private endpoint so nodes talk to the API inside the VPC.
  endpoint_public_access  = true
  endpoint_private_access = true

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
    aws-efs-csi-driver = {
      pod_identity_association = [{
        role_arn        = module.efs_csi_pod_identity.iam_role_arn
        service_account = "efs-csi-controller-sa"
      }]
    }
  }

  # Karpenter finds the node security group by this tag (subnets carry it too).
  node_security_group_tags = {
    "karpenter.sh/discovery" = var.name
  }

  eks_managed_node_groups = {
    system = {
      instance_types = var.system_instance_types
      capacity_type  = "ON_DEMAND"

      min_size     = var.system_node_count
      max_size     = var.system_node_count
      desired_size = var.system_node_count

      labels = {
        role = "system"
      }
    }
  }
}

################################################################################
# Karpenter
# Launches nodes for pods that don't fit, and removes them when idle. The SQS
# queue receives the 2-minute spot interruption notice so nodes drain cleanly.
################################################################################

module "karpenter" {
  source  = "terraform-aws-modules/eks/aws//modules/karpenter"
  version = "~> 21.29"

  cluster_name = module.eks.cluster_name

  # Fixed names so the EC2NodeClass can refer to the node role.
  iam_role_use_name_prefix      = false
  iam_role_name                 = "${var.name}-karpenter-controller"
  node_iam_role_use_name_prefix = false
  node_iam_role_name            = "${var.name}-karpenter-node"
}

resource "helm_release" "karpenter" {
  name       = "karpenter"
  namespace  = "kube-system"
  repository = "oci://public.ecr.aws/karpenter"
  chart      = "karpenter"
  version    = var.karpenter_version

  # The controller calls EC2 at start-up, so its IAM role and Pod Identity
  # association must exist first (otherwise: UnauthorizedOperation, restart).
  depends_on = [module.karpenter]

  values = [yamlencode({
    settings = {
      clusterName       = module.eks.cluster_name
      interruptionQueue = module.karpenter.queue_name
    }
    serviceAccount = {
      name = module.karpenter.service_account
    }
    # Never run the controller on a node it manages.
    nodeSelector = {
      role = "system"
    }
    controller = {
      resources = {
        requests = { cpu = "250m", memory = "512Mi" }
        limits   = { memory = "512Mi" }
      }
    }
  })]
}

################################################################################
# Autoscaling on the vLLM queue
# Prometheus scrapes vllm:num_requests_waiting from annotated pods; KEDA queries
# it and scales the vLLM Deployment. Both run on the system nodes.
################################################################################

resource "helm_release" "prometheus" {
  name             = "prometheus"
  namespace        = "monitoring"
  create_namespace = true
  repository       = "https://prometheus-community.github.io/helm-charts"
  chart            = "prometheus"
  version          = var.prometheus_version

  # Server only: KEDA needs PromQL, nothing else. The default scrape config
  # already picks up pods annotated prometheus.io/scrape=true.
  values = [yamlencode({
    alertmanager             = { enabled = false }
    kube-state-metrics       = { enabled = false }
    prometheus-node-exporter = { enabled = false }
    prometheus-pushgateway   = { enabled = false }
    configmapReload          = { prometheus = { enabled = false } }
    server = {
      retention        = "2h"
      persistentVolume = { enabled = false } # lab: metrics are disposable
      nodeSelector     = { role = "system" }
      resources = {
        requests = { cpu = "100m", memory = "256Mi" }
        limits   = { memory = "512Mi" }
      }
    }
  })]
}

resource "helm_release" "keda" {
  name             = "keda"
  namespace        = "keda"
  create_namespace = true
  repository       = "https://kedacore.github.io/charts"
  chart            = "keda"
  version          = var.keda_version

  values = [yamlencode({
    nodeSelector = { role = "system" }
    resources = {
      operator = {
        requests = { cpu = "100m", memory = "128Mi" }
        limits   = { memory = "256Mi" }
      }
      metricServer = {
        requests = { cpu = "100m", memory = "128Mi" }
        limits   = { memory = "256Mi" }
      }
      webhooks = {
        requests = { cpu = "50m", memory = "64Mi" }
        limits   = { memory = "128Mi" }
      }
    }
  })]
}

output "prometheus_url" {
  description = "In-cluster Prometheus URL for KEDA's prometheus scaler."
  value       = "http://prometheus-server.monitoring.svc.cluster.local"
}

################################################################################
# AWS Load Balancer Controller
# Creates the internal NLB for the vLLM Service (EKS's built-in controller only
# gets critical fixes now; AWS recommends this one for NLBs).
################################################################################

module "lb_controller_pod_identity" {
  source  = "terraform-aws-modules/eks-pod-identity/aws"
  version = "~> 2.10"

  name                            = "${var.name}-lb-controller"
  attach_aws_lb_controller_policy = true

  associations = {
    controller = {
      cluster_name    = module.eks.cluster_name
      namespace       = "kube-system"
      service_account = "aws-load-balancer-controller"
    }
  }
}

resource "helm_release" "lb_controller" {
  name       = "aws-load-balancer-controller"
  namespace  = "kube-system"
  repository = "https://aws.github.io/eks-charts"
  chart      = "aws-load-balancer-controller"
  version    = var.lb_controller_version

  values = [yamlencode({
    clusterName  = module.eks.cluster_name
    region       = data.aws_region.current.region
    vpcId        = var.vpc_id
    replicaCount = 1 # lab: one replica is enough
    serviceAccount = {
      name = "aws-load-balancer-controller"
    }
    nodeSelector = { role = "system" }
    resources = {
      requests = { cpu = "100m", memory = "128Mi" }
      limits   = { memory = "256Mi" }
    }
  })]

  # The controller calls AWS at start-up, so its role must be in place first.
  depends_on = [module.lb_controller_pod_identity]
}

data "aws_region" "current" {}

################################################################################
# Model weights on EFS
# vLLM pods mount this read-many volume, so a new GPU node loads the model from
# inside the VPC instead of downloading it from Hugging Face. Bursting mode has
# no throughput charge; a new file system starts with burst credits.
################################################################################

module "efs" {
  source  = "terraform-aws-modules/efs/aws"
  version = "~> 2.2"

  name            = "${var.name}-models"
  encrypted       = true
  throughput_mode = "bursting"

  # The weights can be re-downloaded, so skip AWS Backup and its storage charge.
  enable_backup_policy = false

  mount_targets = {
    for index, subnet_id in var.private_subnet_ids : "private-${index}" => { subnet_id = subnet_id }
  }

  security_group_name        = "${var.name}-efs"
  security_group_description = "NFS from EKS nodes to the model-weights file system"
  security_group_vpc_id      = var.vpc_id
  security_group_ingress_rules = {
    nfs_from_nodes = {
      description                  = "NFS from EKS nodes"
      referenced_security_group_id = module.eks.node_security_group_id
    }
  }
}

# IAM role the EFS CSI controller uses (via Pod Identity) to create access points.
module "efs_csi_pod_identity" {
  source  = "terraform-aws-modules/eks-pod-identity/aws"
  version = "~> 2.10"

  name                      = "${var.name}-efs-csi"
  attach_aws_efs_csi_policy = true
}

################################################################################
# Outputs
################################################################################

output "cluster_name" {
  description = "Name of the EKS cluster."
  value       = module.eks.cluster_name
}

output "cluster_endpoint" {
  description = "Kubernetes API endpoint."
  value       = module.eks.cluster_endpoint
}

output "cluster_certificate_authority_data" {
  description = "Base64 CA certificate of the cluster."
  value       = module.eks.cluster_certificate_authority_data
}

output "node_security_group_id" {
  description = "Security group shared by the cluster's nodes."
  value       = module.eks.node_security_group_id
}

output "efs_file_system_id" {
  description = "EFS file system holding the model weights (used by the StorageClass)."
  value       = module.efs.id
}

output "karpenter_queue_name" {
  description = "SQS queue Karpenter reads spot interruption notices from."
  value       = module.karpenter.queue_name
}

output "karpenter_node_iam_role_name" {
  description = "IAM role for Karpenter-launched nodes (referenced by the EC2NodeClass)."
  value       = module.karpenter.node_iam_role_name
}
