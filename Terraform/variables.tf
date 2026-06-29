# ==========================================
# TERRAFORM VARIABLES DEFINITION
# ==========================================
# This file defines all input variables that can be customized for different environments
# Variables allow us to reuse the same code for dev, staging, and production

# ==========================================
# PROJECT IDENTIFICATION VARIABLES
# ==========================================
# These variables help identify and organize our infrastructure

# Step 1: Define the main project name
variable "project_name" {
  description = "Name of the project - used as prefix for all resource names"
  type        = string
  default     = "expense"
  # This will be used like: expense-dev-vpc, expense-prod-cluster, etc.
}

# Step 2: Define the environment (dev/staging/prod)
variable "environment" {
  description = "Environment name (dev, staging, prod) - used for resource naming and tagging"
  type        = string
  default     = "dev"
  # Examples: dev, staging, prod, test
}

# Step 3: Define common tags applied to all resources
variable "common_tags" {
  description = "Common tags applied to all AWS resources for cost tracking and management"
  type        = map(string)
  default = {
    Project     = "microservices" # Helps identify which project owns the resource
    Environment = "dev"           # Environment identifier
    Terraform   = "true"          # Indicates resource is managed by Terraform
  }
  # You can add more tags like: Owner, CostCenter, Team, etc.
}

# ==========================================
# EKS CLUSTER CONFIGURATION VARIABLES
# ==========================================
# These variables configure our Kubernetes cluster settings

# Step 4: Define EKS cluster name
variable "cluster_name" {
  description = "Name of the EKS cluster - should be unique in your AWS account"
  type        = string
  default     = "expense-dev"
  # Examples: expense-dev, expense-prod, myapp-staging
}

# Step 5: Define Kubernetes version
variable "eks_version" {
  description = "EKS cluster Kubernetes version - use latest stable version"
  type        = string
  default     = "1.33"
  # AWS regularly updates available versions
  # Check AWS console for latest supported versions
}

# Step 6: Define worker node instance type
variable "node_group_instance_type" {
  description = "EC2 instance type for EKS worker nodes - balance cost vs performance"
  type        = string
  default     = "t3.medium"
  # Common choices:
  # t3.micro (1 vCPU, 1GB RAM) - very small workloads
  # t3.small (2 vCPU, 2GB RAM) - light workloads
  # t3.medium (2 vCPU, 4GB RAM) - moderate workloads
  # m5.large (2 vCPU, 8GB RAM) - production workloads
}

# Step 7: Define desired number of worker nodes
variable "desired_size" {
  description = "Desired number of worker nodes in EKS cluster - target capacity"
  type        = number
  default     = 3
  # 3 nodes needed to run: Jenkins + monitoring + ArgoCD + SonarQube + 3 microservices
}

# Step 8: Define minimum worker nodes
variable "min_size" {
  description = "Minimum number of worker nodes - lowest capacity during scale-down"
  type        = number
  default     = 1
  # Never go below 1 to maintain cluster availability
}

# Step 9: Define maximum worker nodes
variable "max_size" {
  description = "Maximum number of worker nodes - highest capacity during scale-up"
  type        = number
  default     = 4
  # Set based on expected peak load and cost constraints
}

# ==========================================
# NETWORK CONFIGURATION VARIABLES
# ==========================================
# These variables define our network architecture (VPC, subnets)

# Step 10: Define VPC CIDR block
variable "vpc_cidr" {
  description = "CIDR block for VPC - defines the IP address range for entire network"
  type        = string
  default     = "10.0.0.0/16"
  # 10.0.0.0/16 gives us 65,536 IP addresses (10.0.0.0 to 10.0.255.255)
  # Common alternatives: 172.16.0.0/16, 192.168.0.0/16
}

# Step 11: Define public subnet IP ranges
variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets - where load balancers and NAT gateways go"
  type        = list(string)
  default = [
    "10.0.1.0/24", # First public subnet: 10.0.1.0 to 10.0.1.255 (256 IPs)
    "10.0.2.0/24"  # Second public subnet: 10.0.2.0 to 10.0.2.255 (256 IPs)
  ]
  # Public subnets have internet gateway access for inbound/outbound internet traffic
}

# Step 12: Define private subnet IP ranges
variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets - where application pods and worker nodes go"
  type        = list(string)
  default = [
    "10.0.11.0/24", # First private subnet: 10.0.11.0 to 10.0.11.255 (256 IPs)
    "10.0.12.0/24"  # Second private subnet: 10.0.12.0 to 10.0.12.255 (256 IPs)
  ]
  # Private subnets use NAT gateway for outbound internet (more secure)
}

# Step 13: Define database subnet IP ranges
variable "database_subnet_cidrs" {
  description = "CIDR blocks for database subnets - isolated network for RDS databases"
  type        = list(string)
  default = [
    "10.0.21.0/24", # First DB subnet: 10.0.21.0 to 10.0.21.255 (256 IPs)
    "10.0.22.0/24"  # Second DB subnet: 10.0.22.0 to 10.0.22.255 (256 IPs)
  ]
  # Database subnets are most isolated - no internet access, only internal communication
}

# Step 14: Define allowed CIDRs for EKS public API endpoint access
variable "cluster_endpoint_public_access_cidrs" {
  description = "List of CIDR blocks that can access the EKS cluster public API endpoint"
  type        = list(string)
  default     = ["0.0.0.0/0"]
  # Restrict this to known office/VPN CIDRs in production for better security
  # Example: ["203.0.113.0/24", "198.51.100.0/24"]
}