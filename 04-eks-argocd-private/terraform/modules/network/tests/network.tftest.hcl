# Plan-only checks of the private-access wiring. Run: terraform test (from modules/network)

mock_provider "aws" {
  override_data {
    target = data.aws_region.current
    values = { region = "us-east-1" }
  }
}

variables {
  name            = "argocd-test"
  cidr            = "10.20.0.0/16"
  azs             = ["us-east-1a", "us-east-1b"]
  public_subnets  = ["10.20.101.0/24", "10.20.102.0/24"]
  private_subnets = ["10.20.1.0/24", "10.20.2.0/24"]
}

run "capabilities_endpoint_is_an_interface_endpoint_for_the_region" {
  command = plan

  assert {
    condition     = aws_vpc_endpoint.eks_capabilities.service_name == "com.amazonaws.us-east-1.eks-capabilities"
    error_message = "The endpoint must be for the eks-capabilities service in this Region."
  }

  assert {
    condition     = aws_vpc_endpoint.eks_capabilities.vpc_endpoint_type == "Interface"
    error_message = "eks-capabilities is an interface endpoint."
  }
}

run "endpoint_security_group_only_allows_https_from_the_vpc" {
  command = plan

  assert {
    condition     = aws_vpc_security_group_ingress_rule.eks_capabilities_https.cidr_ipv4 == "10.20.0.0/16"
    error_message = "Only the VPC range may reach the endpoint."
  }

  assert {
    condition = (
      aws_vpc_security_group_ingress_rule.eks_capabilities_https.from_port == 443 &&
      aws_vpc_security_group_ingress_rule.eks_capabilities_https.to_port == 443 &&
      aws_vpc_security_group_ingress_rule.eks_capabilities_https.ip_protocol == "tcp"
    )
    error_message = "Only TCP 443 may reach the endpoint."
  }
}
