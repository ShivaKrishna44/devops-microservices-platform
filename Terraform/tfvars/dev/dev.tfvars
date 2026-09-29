project_name             = "platform"
environment              = "dev"
# 10.1.0.0/16 — deliberately different from devops-microservices-crewAi's
# 10.0.0.0/16, so these two clusters' VPCs don't overlap (matters if they're
# ever peered, share a transit gateway, or you want to tell them apart).
vpc_cidr                 = "10.1.0.0/16"
cluster_name             = "platform-dev"
eks_version              = "1.33"
node_group_instance_type = "t3.medium"
desired_size             = 2
max_size                 = 3
min_size                 = 1
public_subnet_cidrs      = ["10.1.1.0/24", "10.1.2.0/24"]
private_subnet_cidrs     = ["10.1.11.0/24", "10.1.12.0/24"]
database_subnet_cidrs    = ["10.1.21.0/24", "10.1.22.0/24"]

