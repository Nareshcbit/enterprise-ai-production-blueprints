# Plan-only checks of the access host. Run: terraform test (from modules/access_host)

mock_provider "aws" {
  override_data {
    target = data.aws_ssm_parameter.al2023_arm64
    values = { value = "ami-0123456789abcdef0" }
  }
}

variables {
  name      = "argocd-test"
  vpc_id    = "vpc-0123456789abcdef0"
  subnet_id = "subnet-0aaaaaaaaaaaaaaaa"
}

run "host_has_no_public_ip_and_no_inbound_rules" {
  command = plan

  assert {
    condition     = aws_instance.this.associate_public_ip_address == false
    error_message = "The access host must not have a public IP."
  }

  assert {
    condition     = length(aws_security_group.this.ingress) == 0
    error_message = "The access host is reached through SSM only; no inbound rules."
  }
}
