# Gateway tier: ECR repo, internal ALB, ECS cluster and the Fargate router service.
# Thin wrapper over terraform-aws-modules/{ecr,alb,ecs}.
# Tags come from the caller's provider default_tags.

terraform {
  required_version = ">= 1.5.7"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.41"
    }
  }
}

################################################################################
# Inputs
################################################################################

variable "name" {
  description = "Name prefix for the gateway resources."
  type        = string
}

variable "vpc_id" {
  description = "VPC to deploy the ALB and tasks into."
  type        = string
}

variable "vpc_cidr_block" {
  description = "VPC CIDR; only callers inside the VPC may reach the internal ALB."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnets for the ALB and the Fargate tasks."
  type        = list(string)
}

variable "image_tag" {
  description = "Router image tag in the ECR repo (tags are immutable)."
  type        = string
}

variable "bedrock_inference_profile_id" {
  description = "Bedrock cross-region inference profile, e.g. us.anthropic.claude-sonnet-5-5."
  type        = string
}

variable "vllm_api_base" {
  description = "OpenAI-compatible base URL of the vLLM service."
  type        = string
}

variable "vllm_metrics_url" {
  description = "Prometheus /metrics URL of the vLLM service, read by the circuit breaker."
  type        = string
}

variable "router_cache_mode" {
  description = "Semantic cache classifier: off, shadow (log only) or active (cache hits route)."
  type        = string
  default     = "shadow"

  validation {
    condition     = contains(["off", "shadow", "active"], var.router_cache_mode)
    error_message = "router_cache_mode must be off, shadow or active."
  }
}

variable "cache_similarity_threshold" {
  description = "Cosine similarity at which a cached routing decision is reused."
  type        = number
  default     = 0.8
}

variable "task_cpu" {
  description = "Fargate task CPU units (1024 = 1 vCPU)."
  type        = number
  default     = 1024
}

variable "task_memory" {
  description = "Fargate task memory in MiB."
  type        = number
  default     = 2048
}

variable "desired_count" {
  description = "Number of router tasks, spread across the private subnets."
  type        = number
  default     = 2
}

################################################################################
# Locals
################################################################################

data "aws_region" "current" {}

data "aws_caller_identity" "current" {}

locals {
  container_name = "litellm-gateway"
  container_port = 4000

  # "us.anthropic.claude-sonnet-5-5" -> "anthropic.claude-sonnet-5-5"
  bedrock_model_id = join(".", slice(split(".", var.bedrock_inference_profile_id), 1, length(split(".", var.bedrock_inference_profile_id))))

  bedrock_inference_profile_arn = "arn:aws:bedrock:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:inference-profile/${var.bedrock_inference_profile_id}"
  # A cross-region profile can serve the request from any of its regions.
  bedrock_foundation_model_arn = "arn:aws:bedrock:*::foundation-model/${local.bedrock_model_id}"
}

################################################################################
# Container registry
################################################################################

module "ecr" {
  source  = "terraform-aws-modules/ecr/aws"
  version = "~> 3.2"

  repository_name = var.name

  # Same-account IAM (CI role, task execution role) is enough; no repo policy.
  create_repository_policy = false
  attach_repository_policy = false

  repository_lifecycle_policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the last 10 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = { type = "expire" }
    }]
  })
}

################################################################################
# Gateway master key (clients send it as a Bearer token)
################################################################################

data "aws_secretsmanager_random_password" "master_key" {
  password_length     = 48
  exclude_punctuation = true
}

resource "aws_secretsmanager_secret" "master_key" {
  name_prefix = "${var.name}-master-key-"
  description = "LiteLLM gateway master key"
}

resource "aws_secretsmanager_secret_version" "master_key" {
  secret_id     = aws_secretsmanager_secret.master_key.id
  secret_string = "sk-${data.aws_secretsmanager_random_password.master_key.random_password}"

  # The data source returns a new value on every plan; keep the first one.
  lifecycle {
    ignore_changes = [secret_string]
  }
}

################################################################################
# Internal ALB
################################################################################

module "alb" {
  source  = "terraform-aws-modules/alb/aws"
  version = "~> 10.5"

  name     = var.name
  vpc_id   = var.vpc_id
  subnets  = var.private_subnet_ids
  internal = true

  enable_deletion_protection = false

  security_group_ingress_rules = {
    http_from_vpc = {
      from_port   = 80
      to_port     = 80
      ip_protocol = "tcp"
      cidr_ipv4   = var.vpc_cidr_block
    }
  }
  security_group_egress_rules = {
    to_vpc = {
      ip_protocol = "-1"
      cidr_ipv4   = var.vpc_cidr_block
    }
  }

  listeners = {
    http = {
      port     = 80
      protocol = "HTTP"
      forward = {
        target_group_key = "router"
      }
    }
  }

  target_groups = {
    router = {
      backend_protocol                  = "HTTP"
      backend_port                      = local.container_port
      target_type                       = "ip"
      deregistration_delay              = 30
      load_balancing_cross_zone_enabled = true

      health_check = {
        enabled             = true
        path                = "/health/liveliness"
        port                = "traffic-port"
        matcher             = "200"
        healthy_threshold   = 2
        unhealthy_threshold = 3
        timeout             = 5
        interval            = 15
      }

      # ECS registers the task IPs itself.
      create_attachment = false
    }
  }
}

################################################################################
# ECS cluster and Fargate service
################################################################################

module "ecs_cluster" {
  source  = "terraform-aws-modules/ecs/aws//modules/cluster"
  version = "~> 7.6"

  name = var.name

  cluster_capacity_providers = ["FARGATE"]
  default_capacity_provider_strategy = {
    FARGATE = {
      weight = 100
    }
  }
}

module "ecs_service" {
  source  = "terraform-aws-modules/ecs/aws//modules/service"
  version = "~> 7.6"

  name        = var.name
  cluster_arn = module.ecs_cluster.arn

  cpu           = var.task_cpu
  memory        = var.task_memory
  desired_count = var.desired_count

  enable_autoscaling     = false
  enable_execute_command = true

  container_definitions = {
    (local.container_name) = {
      cpu       = var.task_cpu
      memory    = var.task_memory
      essential = true
      image     = "${module.ecr.repository_url}:${var.image_tag}"

      portMappings = [{
        name          = local.container_name
        containerPort = local.container_port
        hostPort      = local.container_port
        protocol      = "tcp"
      }]

      environment = [
        { name = "AWS_REGION", value = data.aws_region.current.region },
        { name = "BEDROCK_MODEL", value = "bedrock/converse/${var.bedrock_inference_profile_id}" },
        { name = "VLLM_API_BASE", value = var.vllm_api_base },
        { name = "VLLM_METRICS_URL", value = var.vllm_metrics_url },
        # The judge uses the same Bedrock model, so the task role already covers it.
        { name = "JUDGE_MODEL", value = "bedrock/converse/${var.bedrock_inference_profile_id}" },
        { name = "ROUTER_CACHE_MODE", value = var.router_cache_mode },
        { name = "CACHE_SIMILARITY_THRESHOLD", value = tostring(var.cache_similarity_threshold) },
      ]

      secrets = [
        { name = "LITELLM_MASTER_KEY", valueFrom = aws_secretsmanager_secret.master_key.arn },
      ]

      # LiteLLM writes cache and temp files at startup.
      readonlyRootFilesystem = false
    }
  }

  task_exec_secret_arns = [aws_secretsmanager_secret.master_key.arn]

  tasks_iam_role_statements = [
    {
      sid     = "InvokeRouterModel"
      actions = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
      resources = [
        local.bedrock_inference_profile_arn,
        local.bedrock_foundation_model_arn,
      ]
    }
  ]

  load_balancer = {
    service = {
      target_group_arn = module.alb.target_groups["router"].arn
      container_name   = local.container_name
      container_port   = local.container_port
    }
  }

  subnet_ids = var.private_subnet_ids

  security_group_ingress_rules = {
    from_alb = {
      description                  = "Router port, from the internal ALB only"
      from_port                    = local.container_port
      ip_protocol                  = "tcp"
      referenced_security_group_id = module.alb.security_group_id
    }
  }
  security_group_egress_rules = {
    # Bedrock, ECR and CloudWatch Logs via the NAT gateway until VPC endpoints are on.
    all = {
      ip_protocol = "-1"
      cidr_ipv4   = "0.0.0.0/0"
    }
  }
}

################################################################################
# Outputs
################################################################################

output "alb_dns_name" {
  description = "Internal DNS name of the gateway ALB."
  value       = module.alb.dns_name
}

output "ecr_repository_url" {
  description = "ECR repository to push the router image to."
  value       = module.ecr.repository_url
}

output "cluster_name" {
  description = "ECS cluster name."
  value       = module.ecs_cluster.name
}

output "service_name" {
  description = "ECS service name."
  value       = module.ecs_service.name
}

output "master_key_secret_arn" {
  description = "Secrets Manager secret holding the gateway master key."
  value       = aws_secretsmanager_secret.master_key.arn
}
