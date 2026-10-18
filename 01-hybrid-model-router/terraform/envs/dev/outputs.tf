output "vpc_id" {
  description = "ID of the VPC."
  value       = module.networking.vpc_id
}

output "private_subnet_ids" {
  description = "IDs of the private subnets."
  value       = module.networking.private_subnet_ids
}

output "public_subnet_ids" {
  description = "IDs of the public subnets."
  value       = module.networking.public_subnet_ids
}

output "cloudshell_security_group_id" {
  description = "Security group to pick when creating a CloudShell VPC environment."
  value       = module.networking.cloudshell_security_group_id
}

output "gateway_alb_dns_name" {
  description = "Internal DNS name of the gateway ALB."
  value       = module.gateway.alb_dns_name
}

output "gateway_ecr_repository_url" {
  description = "ECR repository to push the router image to."
  value       = module.gateway.ecr_repository_url
}

output "gateway_cluster_name" {
  description = "ECS cluster running the router."
  value       = module.gateway.cluster_name
}

output "gateway_service_name" {
  description = "ECS service running the router."
  value       = module.gateway.service_name
}

output "gateway_master_key_secret_arn" {
  description = "Secrets Manager secret holding the gateway master key."
  value       = module.gateway.master_key_secret_arn
}

output "eks_cluster_name" {
  description = "Name of the EKS cluster that will host vLLM."
  value       = module.gpu_compute.cluster_name
}

output "eks_cluster_endpoint" {
  description = "Kubernetes API endpoint."
  value       = module.gpu_compute.cluster_endpoint
}

output "efs_file_system_id" {
  description = "EFS file system holding the model weights."
  value       = module.gpu_compute.efs_file_system_id
}

output "karpenter_queue_name" {
  description = "SQS queue for spot interruption notices."
  value       = module.gpu_compute.karpenter_queue_name
}

output "karpenter_node_iam_role_name" {
  description = "IAM role for Karpenter-launched nodes."
  value       = module.gpu_compute.karpenter_node_iam_role_name
}
