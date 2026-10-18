# Networking: VPC, public/private subnets, NAT, and VPC endpoints.
# Thin wrapper over terraform-aws-modules/vpc/aws and its vpc-endpoints submodule.
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
  description = "Name prefix for the VPC and its resources."
  type        = string
}

variable "cidr" {
  description = "IPv4 CIDR block for the VPC."
  type        = string
}

variable "azs" {
  description = "Availability zones to spread subnets across."
  type        = list(string)
}

variable "public_subnets" {
  description = "Public subnet CIDRs, one per AZ (hosts the NAT gateway)."
  type        = list(string)
}

variable "private_subnets" {
  description = "Private subnet CIDRs, one per AZ (hosts ALB, Fargate, EKS nodes, endpoints)."
  type        = list(string)
}

variable "enable_vpc_endpoints" {
  description = "Create interface endpoints for Bedrock Runtime and ECR (~$0.01/hr each per AZ). The S3 gateway endpoint is free and always created."
  type        = bool
  default     = false
}

variable "single_nat_gateway" {
  description = "Use one shared NAT gateway instead of one per AZ. Cheaper; not AZ-resilient."
  type        = bool
  default     = true
}

################################################################################
# VPC
################################################################################

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 6.7"

  name = var.name
  cidr = var.cidr

  azs             = var.azs
  public_subnets  = var.public_subnets
  private_subnets = var.private_subnets

  enable_nat_gateway = true
  single_nat_gateway = var.single_nat_gateway

  enable_dns_hostnames = true
  enable_dns_support   = true

  # Internal load balancers (the vLLM NLB) and Karpenter-launched nodes find
  # these subnets by tag.
  private_subnet_tags = {
    "kubernetes.io/role/internal-elb" = "1"
    "karpenter.sh/discovery"          = var.name
  }
}

################################################################################
# VPC endpoints
# S3 (gateway, free) keeps ECR layer pulls off the NAT gateway. The interface
# endpoints keep Bedrock calls and ECR API traffic off it too, but cost more
# than the NAT traffic they save in a lab, so they're optional.
################################################################################

locals {
  gateway_endpoints = {
    s3 = {
      service         = "s3"
      service_type    = "Gateway"
      route_table_ids = module.vpc.private_route_table_ids
    }
  }

  interface_endpoints = {
    bedrock_runtime = {
      service             = "bedrock-runtime"
      private_dns_enabled = true
    }
    ecr_api = {
      service             = "ecr.api"
      private_dns_enabled = true
    }
    ecr_dkr = {
      service             = "ecr.dkr"
      private_dns_enabled = true
    }
  }
}

module "vpc_endpoints" {
  source  = "terraform-aws-modules/vpc/aws//modules/vpc-endpoints"
  version = "~> 6.7"

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  create_security_group      = var.enable_vpc_endpoints
  security_group_name_prefix = "${var.name}-vpc-endpoints-"
  security_group_description = "HTTPS from inside the VPC to interface endpoints"
  security_group_rules = {
    ingress_https = {
      description = "HTTPS from VPC"
      cidr_blocks = [module.vpc.vpc_cidr_block]
    }
  }

  endpoints = merge(
    local.gateway_endpoints,
    var.enable_vpc_endpoints ? local.interface_endpoints : {},
  )
}

################################################################################
# CloudShell VPC environment
# Lets a console user test internal endpoints (e.g. the gateway ALB) from inside
# the VPC. Outbound only; nothing can connect in.
################################################################################

resource "aws_security_group" "cloudshell" {
  name_prefix = "${var.name}-cloudshell-"
  description = "CloudShell VPC environment: outbound only"
  vpc_id      = module.vpc.vpc_id

  tags = {
    Name = "${var.name}-cloudshell"
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_vpc_security_group_egress_rule" "cloudshell_all" {
  security_group_id = aws_security_group.cloudshell.id
  description       = "All outbound (VPC targets, and AWS APIs via NAT)"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

################################################################################
# Outputs
################################################################################

output "cloudshell_security_group_id" {
  description = "Security group to pick when creating a CloudShell VPC environment."
  value       = aws_security_group.cloudshell.id
}

output "vpc_id" {
  description = "ID of the VPC."
  value       = module.vpc.vpc_id
}

output "vpc_cidr_block" {
  description = "CIDR block of the VPC."
  value       = module.vpc.vpc_cidr_block
}

output "public_subnet_ids" {
  description = "IDs of the public subnets."
  value       = module.vpc.public_subnets
}

output "private_subnet_ids" {
  description = "IDs of the private subnets."
  value       = module.vpc.private_subnets
}

output "vpc_endpoint_security_group_id" {
  description = "Security group attached to the interface endpoints (null when disabled)."
  value       = module.vpc_endpoints.security_group_id
}
