variable "region" {
  description = "AWS region to deploy into."
  type        = string
}

variable "name" {
  description = "Name prefix for all resources."
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

variable "single_nat_gateway" {
  description = "Use one shared NAT gateway instead of one per AZ."
  type        = bool
}

variable "enable_vpc_endpoints" {
  description = "Create the Bedrock and ECR interface endpoints."
  type        = bool
}

variable "tags" {
  description = "Default tags applied to every resource."
  type        = map(string)
}

variable "gateway_image_tag" {
  description = "Router image tag to deploy from the gateway ECR repo."
  type        = string
}

variable "bedrock_inference_profile_id" {
  description = "Bedrock cross-region inference profile the router calls for complex requests."
  type        = string
}

variable "vllm_api_base" {
  description = "OpenAI-compatible base URL of the vLLM service."
  type        = string
}

variable "vllm_metrics_url" {
  description = "Prometheus /metrics URL of the vLLM service."
  type        = string
}

variable "router_cache_mode" {
  description = "Semantic cache classifier: off, shadow (log only) or active (cache hits route)."
  type        = string
}

variable "kubernetes_version" {
  description = "Kubernetes version of the EKS control plane."
  type        = string
}

variable "eks_access_entries" {
  description = "IAM principals allowed into the EKS cluster; access is admin or view."
  type = map(object({
    principal_arn = string
    access        = string
  }))
}

variable "karpenter_version" {
  description = "Karpenter Helm chart version."
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
