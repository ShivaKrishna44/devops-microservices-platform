# ==========================================
# IRSA (IAM Roles for Service Accounts)
# ==========================================
# This file creates IAM roles for Kubernetes service accounts to access AWS services
# without storing AWS credentials in pods (more secure approach)

# ==========================================
# EBS CSI Driver IAM Role Setup
# ==========================================

#Step 1: Define who can assume the EBS CSI role (trust policy)
data "aws_iam_policy_document" "ebs_csi_assume_role" {
  statement {
    # Action: Allow assuming role with web identity (OIDC)
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type = "Federated"
      # This points to our EKS cluster's OIDC provider
      identifiers = [module.eks.oidc_provider_arn]
    }

    # Security: Only allow specific service account to use this role
    condition {
      test     = "StringEquals"
      variable = "${module.eks.oidc_provider}:sub"
      values = [
        # Only ebs-csi-controller-sa in kube-system namespace can use this role
        "system:serviceaccount:kube-system:ebs-csi-controller-sa"
      ]
    }

    # Additional security: Verify the request comes from AWS STS
    condition {
      test     = "StringEquals"
      variable = "${module.eks.oidc_provider}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

#Step 2: Create the actual IAM role for EBS CSI driver
resource "aws_iam_role" "ebs_csi" {
  name = "${var.project_name}-${var.environment}-ebs-csi-role"
  # Use the trust policy we defined above
  assume_role_policy = data.aws_iam_policy_document.ebs_csi_assume_role.json

  # Add tags for identification and management
  tags = merge(var.common_tags, {
    Name        = "${var.project_name}-${var.environment}-ebs-csi-role"
    Purpose     = "EBS CSI Driver IRSA Role"
    ServiceType = "Storage"
  })
}

# Step 3: Attach AWS managed policy that gives EBS permissions
resource "aws_iam_role_policy_attachment" "ebs_csi" {
  role = aws_iam_role.ebs_csi.name
  # AWS pre-built policy with all EBS CSI driver permissions
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"
}

# ==========================================
# AWS Load Balancer Controller IAM Role Setup
# ==========================================

# Step 1: Define who can assume the ALB Controller role (trust policy)
data "aws_iam_policy_document" "alb_controller_assume_role" {
  statement {
    # Action: Allow assuming role with web identity (OIDC)
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type = "Federated"
      # This points to our EKS cluster's OIDC provider
      identifiers = [module.eks.oidc_provider_arn]
    }

    # Security: Only allow specific service account to use this role
    condition {
      test     = "StringEquals"
      variable = "${module.eks.oidc_provider}:sub"
      values = [
        # Only aws-load-balancer-controller in kube-system namespace can use this role
        "system:serviceaccount:kube-system:aws-load-balancer-controller"
      ]
    }

    # Additional security: Verify the request comes from AWS STS
    condition {
      test     = "StringEquals"
      variable = "${module.eks.oidc_provider}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

# Step 2: Create the actual IAM role for ALB Controller
resource "aws_iam_role" "alb_controller" {
  name = "${var.project_name}-${var.environment}-alb-controller-role"
  # Use the trust policy we defined above
  assume_role_policy = data.aws_iam_policy_document.alb_controller_assume_role.json

  # Add tags for identification and management
  tags = merge(var.common_tags, {
    Name        = "${var.project_name}-${var.environment}-alb-controller-role"
    Purpose     = "AWS Load Balancer Controller IRSA Role"
    ServiceType = "Networking"
  })
}

# Step 3: Create custom IAM policy for ALB Controller
# (ALB Controller needs many permissions, so we use a custom policy file)
resource "aws_iam_policy" "alb_controller" {
  name        = "${var.project_name}-${var.environment}-alb-controller-policy"
  description = "Custom IAM Policy for AWS Load Balancer Controller"
  # This reads the policy from a JSON file in the policies/ folder
  # create a file mkdir -p policies and run curl -o policies/aws-load-balancer-controller.json \
  # https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/main/docs/install/iam_policy.json
  # .json file creates automatically.
  policy = file("${path.module}/policies/aws-load-balancer-controller.json")

  # Add tags for identification and management
  tags = merge(var.common_tags, {
    Name        = "${var.project_name}-${var.environment}-alb-controller-policy"
    Purpose     = "AWS Load Balancer Controller Policy"
    ServiceType = "Networking"
  })
}

# Step 4: Attach our custom policy to the ALB Controller role
resource "aws_iam_role_policy_attachment" "alb_controller" {
  role = aws_iam_role.alb_controller.name
  # Use our custom policy (not AWS managed policy)
  policy_arn = aws_iam_policy.alb_controller.arn
}