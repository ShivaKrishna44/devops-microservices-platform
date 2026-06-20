#==========================================
#Data Sources
# ==========================================
data "aws_ssm_parameter" "private_subnet_ids" {
  name = "/${var.project_name}/${var.environment}/private_subnet_ids"
}

data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}