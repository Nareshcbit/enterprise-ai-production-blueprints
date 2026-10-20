output "cluster_name" {
  description = "EKS cluster name."
  value       = module.cluster.cluster_name
}

output "cluster_arn" {
  description = "EKS cluster ARN; Argo CD registers the hub by this ARN."
  value       = module.cluster.cluster_arn
}

output "argocd_server_url" {
  description = "Argo CD UI and API URL. Resolves to private IPs; reachable only from the VPC."
  value       = module.argocd.server_url
}

output "argocd_capability_role_arn" {
  description = "Capability IAM role; the principal Argo CD uses on every target cluster."
  value       = module.argocd.capability_role_arn
}

output "eks_capabilities_vpce_id" {
  description = "The eks-capabilities interface endpoint."
  value       = module.network.eks_capabilities_vpce_id
}

output "access_host_id" {
  description = "SSM-only instance inside the VPC, for checks and port forwarding."
  value       = module.access_host.instance_id
}
