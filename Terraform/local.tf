# ==========================================
# Local Values
# ==========================================
locals {
  eks_managed_node_groups = {
    "${var.environment}" = {
      instance_types = [var.node_group_instance_type]
      desired_size   = var.desired_size
      min_size       = var.min_size
      max_size       = var.max_size
      
      iam_role_arn = aws_iam_role.node_group.arn
    }
  }
}