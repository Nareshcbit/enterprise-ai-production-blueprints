variable "region" {
  description = "AWS region to deploy into."
  type        = string
}

variable "name" {
  description = "Name prefix for all resources (also the EKS cluster name)."
  type        = string
}

variable "vpc_cidr" {
  description = "IPv4 CIDR block for the VPC."
  type        = string
}

variable "azs" {
  description = "Availability zones to spread subnets across."
  type        = list(string)
}

variable "public_subnets" {
  description = "Public subnet CIDRs, one per AZ."
  type        = list(string)
}

variable "private_subnets" {
  description = "Private subnet CIDRs, one per AZ."
  type        = list(string)
}

variable "tags" {
  description = "Default tags applied to every resource."
  type        = map(string)
}

variable "kubernetes_version" {
  description = "Kubernetes version of the EKS control plane."
  type        = string
}

variable "public_access_cidrs" {
  description = "CIDRs allowed to reach the public Kubernetes API (your workstation's IPv4 /32)."
  type        = list(string)
}

variable "eks_access_entries" {
  description = "IAM principals allowed into the EKS cluster; access is admin or view."
  type = map(object({
    principal_arn = string
    access        = string
  }))
}

variable "idc_instance_arn" {
  description = "IAM Identity Center instance ARN."
  type        = string
}

variable "idc_region" {
  description = "Region of the Identity Center instance."
  type        = string
}

variable "argocd_admin_identity" {
  description = "Identity Center user or group mapped to the Argo CD ADMIN role (type SSO_USER or SSO_GROUP)."
  type = object({
    id   = string
    type = string
  })
}

variable "deploy_namespace" {
  description = "Namespace on the hub where Argo CD may deploy (the sample app's namespace)."
  type        = string
}
