terraform {
  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.45"
    }
  }

  # Experimental environments use a SEPARATE state file from production.
  # State is stored in the same Hetzner Object Storage bucket under a
  # per-experiment key. This preserves D-022 (experimental zone on separate
  # infrastructure) at the state level — experimental state never touches
  # the production state file.
  #
  # Backend configuration must be supplied at init time:
  #   terraform init \
  #     -backend-config="key=experimental/${var.experiment_name}/terraform.tfstate"
  #     -backend-config="access_key=<HETZNER_OBJ_KEY>" \
  #     -backend-config="secret_key=<HETZNER_OBJ_SECRET>"
  #
  # See README.md for full initialisation instructions.
  backend "s3" {
    endpoints = {
      s3 = "https://fsn1.your-objectstorage.com"
    }
    bucket                      = "clive-terraform-state"
    # key is set per-experiment at init time — see README.md
    region                      = "main"
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    use_path_style              = true
  }

  required_version = ">= 1.6"
}

provider "hcloud" {
  token = var.hcloud_token
}

# SSH key — registered per experiment to allow owner access.
resource "hcloud_ssh_key" "experimental" {
  name       = "clive-exp-${var.experiment_name}"
  public_key = var.ssh_public_key

  labels = {
    environment = "experimental"
    experiment  = var.experiment_name
    managed_by  = "terraform"
  }
}

# Firewall — restrictive by design. Only owner SSH and outbound HTTPS.
# Experimental environments do not expose HTTP/HTTPS publicly (D-022).
resource "hcloud_firewall" "experimental" {
  name = "clive-exp-${var.experiment_name}"

  # SSH from owner IP only
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "22"
    source_ips = [var.owner_ip]
    description = "Owner SSH access"
  }

  labels = {
    environment = "experimental"
    experiment  = var.experiment_name
    managed_by  = "terraform"
  }
}

# Experimental VM — isolated from production network.
# Same Hetzner account as production but no shared resources.
resource "hcloud_server" "experimental" {
  name        = "clive-exp-${var.experiment_name}"
  server_type = var.server_type
  image       = "ubuntu-24.04"
  location    = var.location

  ssh_keys    = [hcloud_ssh_key.experimental.id]
  firewall_ids = [hcloud_firewall.experimental.id]

  labels = {
    environment = "experimental"
    experiment  = var.experiment_name
    managed_by  = "terraform"
    # Block 21 evolution engine sets this label to track which experiment
    # is running. Do not modify manually.
    block21_experiment = var.experiment_name
  }

  # User data — minimal setup: install Docker and pull sandbox image.
  # Block 21 handles further configuration via the controlled event bridge (D-024).
  user_data = <<-EOF
    #!/bin/bash
    set -e
    apt-get update -qq
    apt-get install -y -qq docker.io
    systemctl enable docker
    systemctl start docker
    # Label this host so the event bridge can identify it
    echo "CLIVE_EXPERIMENT_NAME=${var.experiment_name}" >> /etc/environment
    echo "CLIVE_ENV=experimental" >> /etc/environment
  EOF
}
