variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "eu-west-1" # Ireland — closest to Dublin
}

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "dublin-bikes"
}

variable "ec2_instance_type" {
  type    = string
  default = "t3.small"
}

variable "rds_instance_class" {
  type    = string
  default = "db.t3.micro"
}

variable "db_name" {
  type    = string
  default = "softwaredb"
}

variable "db_username" {
  type    = string
  default = "admin"
}

variable "db_password" {
  description = "RDS MySQL root password"
  type        = string
  sensitive   = true
}

variable "jcdecaux_api_key" {
  type      = string
  sensitive = true
}

variable "jcdecaux_contract_name" {
  type    = string
  default = "dublin"
}

variable "openweather_api_key" {
  type      = string
  sensitive = true
}

variable "city_name" {
  type    = string
  default = "Dublin"
}

variable "ssh_public_key_path" {
  description = "Path to your local SSH public key (e.g. ~/.ssh/id_rsa.pub)"
  type        = string
  default     = "~/.ssh/id_rsa.pub"
}
