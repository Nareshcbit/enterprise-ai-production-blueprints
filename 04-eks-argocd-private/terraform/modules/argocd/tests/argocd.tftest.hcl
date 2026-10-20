# Plan-only checks of the Argo CD capability. Run: terraform test (from modules/argocd)

mock_provider "aws" {}

variables {
  name             = "argocd-test"
  cluster_name     = "argocd-test"
  vpce_id          = "vpce-0123456789abcdef0"
  idc_instance_arn = "arn:aws:sso:::instance/ssoins-1234567890abcdef"
  idc_region       = "us-east-1"
  admin_identity   = { id = "c4081448-0000-0000-0000-000000000000", type = "SSO_USER" }
  deploy_namespace = "guestbook"
}

run "capability_is_private_through_the_vpc_endpoint" {
  command = plan

  assert {
    condition     = aws_eks_capability.argocd.type == "ARGOCD"
    error_message = "The capability must be Argo CD."
  }

  assert {
    condition     = one(one(one(aws_eks_capability.argocd.configuration).argo_cd).network_access).vpce_ids == toset(["vpce-0123456789abcdef0"])
    error_message = "The capability must list the VPC endpoint, which blocks public access."
  }
}

run "admin_identity_maps_to_admin_role" {
  command = plan

  assert {
    condition = anytrue([
      for m in one(one(aws_eks_capability.argocd.configuration).argo_cd).rbac_role_mapping :
      m.role == "ADMIN" && anytrue([for i in m.identity : i.id == "c4081448-0000-0000-0000-000000000000" && i.type == "SSO_USER"])
    ])
    error_message = "The admin identity must be mapped to ADMIN."
  }
}

run "capability_role_trusts_only_eks_capabilities" {
  command = plan

  assert {
    condition     = jsondecode(aws_iam_role.capability.assume_role_policy).Statement[0].Principal.Service == "capabilities.eks.amazonaws.com"
    error_message = "The role must be assumable only by the EKS capabilities service."
  }
}

run "hub_write_access_is_namespace_scoped_not_cluster_admin" {
  command = plan

  assert {
    condition     = aws_eks_access_policy_association.deploy.policy_arn == "arn:aws:eks::aws:cluster-access-policy/AmazonEKSEditPolicy"
    error_message = "Write access must use the Edit policy, never cluster admin."
  }

  assert {
    condition = (
      aws_eks_access_policy_association.deploy.access_scope[0].type == "namespace" &&
      aws_eks_access_policy_association.deploy.access_scope[0].namespaces == toset(["guestbook"])
    )
    error_message = "Write access must be limited to the deploy namespace."
  }
}

run "hub_read_access_is_cluster_wide_and_read_only" {
  command = plan

  assert {
    condition     = aws_eks_access_policy_association.read.policy_arn == "arn:aws:eks::aws:cluster-access-policy/AmazonEKSAdminViewPolicy"
    error_message = "Argo CD needs read access to every resource type for health checks and drift detection."
  }

  assert {
    condition     = aws_eks_access_policy_association.read.access_scope[0].type == "cluster"
    error_message = "Read access must be cluster-wide."
  }
}
