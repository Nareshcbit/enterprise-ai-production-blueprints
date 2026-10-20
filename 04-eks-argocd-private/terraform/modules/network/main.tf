# Networking: VPC, public/private subnets, one NAT gateway, and the interface
# endpoint that makes the Argo CD capability private.
# Thin wrapper over terraform-aws-modules/vpc/aws; the endpoint is plain resources.
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
  description = "Public subnet CIDRs, one per AZ (hosts the NAT gateway only)."
  type        = list(string)
}

variable "private_subnets" {
  description = "Private subnet CIDRs, one per AZ (EKS nodes, the access host, the eks-capabilities endpoint)."
  type        = list(string)
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
  single_nat_gateway = true

  enable_dns_hostnames = true
  enable_dns_support   = true
}

################################################################################
# eks-capabilities interface endpoint
# Listing its ID on the Argo CD capability blocks public access; AWS then
# points the capability's hostname at this endpoint's private IPs. Endpoint
# policies aren't supported for this service, so the security group is the
# only network filter.
################################################################################

data "aws_region" "current" {}

resource "aws_security_group" "eks_capabilities" {
  name_prefix = "${var.name}-eks-capabilities-"
  description = "HTTPS to the Argo CD capability endpoint"
  vpc_id      = module.vpc.vpc_id

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_vpc_security_group_ingress_rule" "eks_capabilities_https" {
  security_group_id = aws_security_group.eks_capabilities.id
  description       = "HTTPS from the VPC"
  cidr_ipv4         = var.cidr
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

resource "aws_vpc_endpoint" "eks_capabilities" {
  vpc_id              = module.vpc.vpc_id
  service_name        = "com.amazonaws.${data.aws_region.current.region}.eks-capabilities"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = module.vpc.private_subnets
  security_group_ids  = [aws_security_group.eks_capabilities.id]
  private_dns_enabled = false # AWS manages the capability's DNS records itself

  tags = {
    Name = "${var.name}-eks-capabilities"
  }
}

################################################################################
# Outputs
################################################################################

output "vpc_id" {
  description = "VPC ID."
  value       = module.vpc.vpc_id
}

output "private_subnet_ids" {
  description = "Private subnet IDs."
  value       = module.vpc.private_subnets
}

output "eks_capabilities_vpce_id" {
  description = "ID of the eks-capabilities interface endpoint."
  value       = aws_vpc_endpoint.eks_capabilities.id
}
