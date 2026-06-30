# --------------------------------------------------------------------------
# Chaos Engineering Toolkit — Terraform
# Deploys the chaos runner as a K8s CronJob with IAM role for Bedrock access
# --------------------------------------------------------------------------

terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.25"
    }
  }

  backend "s3" {
    bucket         = "chaos-engineering-tfstate"
    key            = "chaos-runner/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "terraform-locks"
    encrypt        = true
  }
}

# --------------------------------------------------------------------------
# Providers
# --------------------------------------------------------------------------

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "chaos-engineering"
      ManagedBy   = "terraform"
      Environment = var.environment
    }
  }
}

provider "kubernetes" {
  host                   = data.aws_eks_cluster.cluster.endpoint
  cluster_ca_certificate = base64decode(data.aws_eks_cluster.cluster.certificate_authority[0].data)
  token                  = data.aws_eks_cluster_auth.cluster.token
}

# --------------------------------------------------------------------------
# Variables
# --------------------------------------------------------------------------

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "production"
}

variable "cluster_name" {
  description = "EKS cluster name"
  type        = string
}

variable "chaos_namespace" {
  description = "Kubernetes namespace for the chaos runner"
  type        = string
  default     = "chaos-engineering"
}

variable "chaos_schedule" {
  description = "CronJob schedule expression"
  type        = string
  default     = "0 2 * * 1" # Every Monday at 2 AM
}

variable "chaos_image" {
  description = "Container image for the chaos runner"
  type        = string
  default     = "ghcr.io/xops/chaos-engineering:latest"
}

variable "experiment_manifest" {
  description = "Path to the experiment manifest inside the container"
  type        = string
  default     = "/app/manifests/experiment-pod-kill.yml"
}

variable "bedrock_model_id" {
  description = "AWS Bedrock model ID for AI analysis"
  type        = string
  default     = "anthropic.claude-3-sonnet-20240229-v1:0"
}

variable "dry_run" {
  description = "Run experiments in dry-run mode"
  type        = bool
  default     = false
}

# --------------------------------------------------------------------------
# Data sources
# --------------------------------------------------------------------------

data "aws_caller_identity" "current" {}

data "aws_eks_cluster" "cluster" {
  name = var.cluster_name
}

data "aws_eks_cluster_auth" "cluster" {
  name = var.cluster_name
}

# --------------------------------------------------------------------------
# IAM — IRSA for Bedrock access
# --------------------------------------------------------------------------

data "aws_iam_policy_document" "chaos_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type = "Federated"
      identifiers = [
        "arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/${replace(data.aws_eks_cluster.cluster.identity[0].oidc[0].issuer, "https://", "")}"
      ]
    }

    condition {
      test     = "StringEquals"
      variable = "${replace(data.aws_eks_cluster.cluster.identity[0].oidc[0].issuer, "https://", "")}:sub"
      values   = ["system:serviceaccount:${var.chaos_namespace}:chaos-runner"]
    }
  }
}

resource "aws_iam_role" "chaos_runner" {
  name               = "chaos-runner-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.chaos_assume_role.json
}

data "aws_iam_policy_document" "bedrock_access" {
  statement {
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
    ]
    resources = ["arn:aws:bedrock:${var.aws_region}::foundation-model/${var.bedrock_model_id}"]
  }
}

resource "aws_iam_role_policy" "bedrock" {
  name   = "bedrock-access"
  role   = aws_iam_role.chaos_runner.id
  policy = data.aws_iam_policy_document.bedrock_access.json
}

# --------------------------------------------------------------------------
# Kubernetes resources
# --------------------------------------------------------------------------

resource "kubernetes_namespace" "chaos" {
  metadata {
    name = var.chaos_namespace
    labels = {
      "app.kubernetes.io/managed-by" = "terraform"
      "app.kubernetes.io/part-of"    = "chaos-engineering"
    }
  }
}

resource "kubernetes_service_account" "chaos_runner" {
  metadata {
    name      = "chaos-runner"
    namespace = kubernetes_namespace.chaos.metadata[0].name
    annotations = {
      "eks.amazonaws.com/role-arn" = aws_iam_role.chaos_runner.arn
    }
    labels = {
      "app.kubernetes.io/name" = "chaos-runner"
    }
  }
}

resource "kubernetes_cluster_role" "chaos_runner" {
  metadata {
    name = "chaos-runner"
  }

  # Pod operations for pod-kill, cpu-stress, network-latency, disk-fill
  rule {
    api_groups = [""]
    resources  = ["pods", "pods/log"]
    verbs      = ["get", "list", "watch", "create", "delete"]
  }

  # ConfigMap operations for dns-failure (CoreDNS patching)
  rule {
    api_groups = [""]
    resources  = ["configmaps"]
    verbs      = ["get", "list", "update", "patch"]
  }

  # Deployment operations for CoreDNS restart
  rule {
    api_groups = ["apps"]
    resources  = ["deployments"]
    verbs      = ["get", "patch"]
  }
}

resource "kubernetes_cluster_role_binding" "chaos_runner" {
  metadata {
    name = "chaos-runner"
  }

  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "ClusterRole"
    name      = kubernetes_cluster_role.chaos_runner.metadata[0].name
  }

  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account.chaos_runner.metadata[0].name
    namespace = kubernetes_namespace.chaos.metadata[0].name
  }
}

resource "kubernetes_cron_job_v1" "chaos_runner" {
  metadata {
    name      = "chaos-runner"
    namespace = kubernetes_namespace.chaos.metadata[0].name
    labels = {
      "app.kubernetes.io/name"    = "chaos-runner"
      "app.kubernetes.io/part-of" = "chaos-engineering"
    }
  }

  spec {
    schedule                      = var.chaos_schedule
    concurrency_policy            = "Forbid"
    successful_jobs_history_limit = 5
    failed_jobs_history_limit     = 3

    job_template {
      metadata {
        labels = {
          "app.kubernetes.io/name" = "chaos-runner"
        }
      }

      spec {
        backoff_limit = 1

        template {
          metadata {
            labels = {
              "app.kubernetes.io/name" = "chaos-runner"
            }
          }

          spec {
            service_account_name = kubernetes_service_account.chaos_runner.metadata[0].name

            container {
              name  = "chaos-runner"
              image = var.chaos_image

              command = ["python", "-m", "src.runner.cli"]

              args = compact([
                "--manifest", var.experiment_manifest,
                "--analyze",
                var.dry_run ? "--dry-run" : "",
              ])

              env {
                name  = "BEDROCK_MODEL_ID"
                value = var.bedrock_model_id
              }

              env {
                name  = "AWS_DEFAULT_REGION"
                value = var.aws_region
              }

              resources {
                requests = {
                  cpu    = "100m"
                  memory = "128Mi"
                }
                limits = {
                  cpu    = "500m"
                  memory = "256Mi"
                }
              }
            }

            restart_policy = "Never"
          }
        }
      }
    }
  }
}

# --------------------------------------------------------------------------
# Outputs
# --------------------------------------------------------------------------

output "iam_role_arn" {
  description = "IAM role ARN for the chaos runner"
  value       = aws_iam_role.chaos_runner.arn
}

output "namespace" {
  description = "Kubernetes namespace for the chaos runner"
  value       = kubernetes_namespace.chaos.metadata[0].name
}

output "cronjob_schedule" {
  description = "CronJob schedule"
  value       = var.chaos_schedule
}
