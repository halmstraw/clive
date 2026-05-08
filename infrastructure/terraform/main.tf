terraform {
  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.45"
    }
  }

  backend "s3" {
    # Hetzner Object Storage S3-compatible backend
    # Bootstrap this bucket manually before first terraform apply
    # See docs/runbooks/terraform-bootstrap.md
    endpoint                    = "https://fsn1.your-objectstorage.com"
    bucket                      = "clive-terraform-state"
    key                         = "v0.1/terraform.tfstate"
    region                      = "main"
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_region_validation      = true
    force_path_style            = true
  }

  required_version = ">= 1.6"
}

provider "hcloud" {
  token = var.hcloud_token
}

# SSH key
resource "hcloud_ssh_key" "clive_owner" {
  name       = "clive-owner"
  public_key = var.ssh_public_key
}

# Firewall — inbound SSH from owner IP only; all other inbound blocked
# Telegram bot uses outbound HTTPS only — no inbound rules needed
resource "hcloud_firewall" "clive" {
  name = "clive-v01"

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "22"
    source_ips = ["${var.owner_ip}/32"]
  }

  rule {
    direction       = "out"
    protocol        = "tcp"
    port            = "any"
    destination_ips = ["0.0.0.0/0", "::/0"]
  }

  rule {
    direction       = "out"
    protocol        = "udp"
    port            = "any"
    destination_ips = ["0.0.0.0/0", "::/0"]
  }
}

# VM
resource "hcloud_server" "clive" {
  name        = "clive-v01"
  server_type = "cx21"
  image       = "ubuntu-24.04"
  location    = "fsn1"

  ssh_keys = [hcloud_ssh_key.clive_owner.id]

  firewall_ids = [hcloud_firewall.clive.id]

  # Hetzner automated daily backup — satisfies D-056 nightly snapshot
  backups = true

  labels = {
    environment = "production"
    block       = "infrastructure"
    zone        = "personal"
    category    = "compute"
  }

  user_data = <<-EOF
    #!/bin/bash
    # Disable root password login
    sed -i 's/^PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
    systemctl restart sshd
  EOF
}
