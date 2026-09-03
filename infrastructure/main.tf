terraform {
  required_providers {
    null = {
      source  = "hashicorp/null"
      version = "~> 3.2"
    }
  }
}

provider "null" {}

resource "null_resource" "test" {
  provisioner "local-exec" {
    command = "echo Terraform is working"
  }
}
