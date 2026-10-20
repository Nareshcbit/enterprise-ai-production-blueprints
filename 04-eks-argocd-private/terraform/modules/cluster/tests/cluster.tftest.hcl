# Input validation for the cluster module. Run: terraform test (from modules/cluster)

mock_provider "aws" {}

# Only the module's own input validation is under test, not the upstream EKS module.
override_module {
  target = module.eks
  outputs = {
    cluster_name = "argocd-test"
    cluster_arn  = "arn:aws:eks:us-east-1:111122223333:cluster/argocd-test"
  }
}

variables {
  name               = "argocd-test"
  kubernetes_version = "1.37"
  vpc_id             = "vpc-0123456789abcdef0"
  private_subnet_ids = ["subnet-0aaaaaaaaaaaaaaaa", "subnet-0bbbbbbbbbbbbbbbb"]
}

run "public_api_open_to_the_internet_is_rejected" {
  command = plan

  variables {
    public_access_cidrs = ["0.0.0.0/0"]
  }

  expect_failures = [var.public_access_cidrs]
}

run "workstation_cidr_is_accepted" {
  command = plan

  variables {
    public_access_cidrs = ["203.0.113.10/32"]
  }
}

run "public_api_needs_at_least_one_cidr" {
  command = plan

  variables {
    public_access_cidrs = []
  }

  expect_failures = [var.public_access_cidrs]
}
