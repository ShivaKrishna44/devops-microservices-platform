project_name             = "expense"
environment              = "dev"
vpc_cidr                 = "10.0.0.0/16"
cluster_name             = "expense-dev"
eks_version              = "1.33"
node_group_instance_type = "t3.medium"
desired_size             = 2
max_size                 = 3
min_size                 = 1
public_subnet_cidrs      = ["10.0.1.0/24", "10.0.2.0/24"]
private_subnet_cidrs     = ["10.0.11.0/24", "10.0.12.0/24"]
database_subnet_cidrs    = ["10.0.21.0/24", "10.0.22.0/24"]

