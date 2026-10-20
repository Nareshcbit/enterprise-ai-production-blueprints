# A small instance inside the VPC, reached only through SSM Session Manager.
# With public access blocked, it's how you reach Argo CD without a VPN or
# Direct Connect: run checks on it, or port-forward through it to your browser.
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
  description = "Name prefix for the instance and its IAM role."
  type        = string
}

variable "vpc_id" {
  description = "VPC to launch the instance in."
  type        = string
}

variable "subnet_id" {
  description = "Private subnet for the instance (reaches SSM through the NAT gateway)."
  type        = string
}

variable "instance_type" {
  description = "Instance type (arm64)."
  type        = string
  default     = "t4g.nano"
}

################################################################################
# Instance
################################################################################

data "aws_ssm_parameter" "al2023_arm64" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

resource "aws_iam_role" "this" {
  name = "${var.name}-access-host"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.this.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "this" {
  name = "${var.name}-access-host"
  role = aws_iam_role.this.name
}

# Outbound only: SSM and the Argo CD endpoint. No inbound rules.
resource "aws_security_group" "this" {
  name_prefix = "${var.name}-access-host-"
  description = "Access host: outbound only"
  vpc_id      = var.vpc_id

  ingress = []

  egress {
    description = "All outbound"
    protocol    = "-1"
    from_port   = 0
    to_port     = 0
    cidr_blocks = ["0.0.0.0/0"]
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_instance" "this" {
  ami                         = data.aws_ssm_parameter.al2023_arm64.value
  instance_type               = var.instance_type
  subnet_id                   = var.subnet_id
  vpc_security_group_ids      = [aws_security_group.this.id]
  iam_instance_profile        = aws_iam_instance_profile.this.name
  associate_public_ip_address = false

  metadata_options {
    http_tokens = "required"
  }

  tags = {
    Name = "${var.name}-access-host"
  }
}

################################################################################
# Outputs
################################################################################

output "instance_id" {
  description = "Access host instance ID (target for SSM sessions)."
  value       = aws_instance.this.id
}
