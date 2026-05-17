# Block 24 — Experimental environment variables (v1.0, D-152)
# Parameterised per D-029: Block 21 provisions environments using these templates.
# All values must be supplied at apply time — no hardcoded production values.

variable "hcloud_token" {
  description = "Hetzner Cloud API token for the experimental account (NOT the production token)."
  type        = string
  sensitive   = true
}

variable "ssh_public_key" {
  description = "SSH public key for owner access to the experimental VM."
  type        = string
}

variable "experiment_name" {
  description = "Unique name for this experimental environment. Used in resource labels and hostnames. e.g. 'exp-001', 'evolution-test-1'. Must be lowercase alphanumeric with hyphens."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{0,30}[a-z0-9]$", var.experiment_name))
    error_message = "experiment_name must be lowercase alphanumeric with hyphens, 2-32 chars."
  }
}

variable "server_type" {
  description = "Hetzner server type for the experimental VM. Use smallest type that fits the workload."
  type        = string
  default     = "cx21"
}

variable "location" {
  description = "Hetzner datacenter location for the experimental VM."
  type        = string
  default     = "fsn1"
}

variable "owner_ip" {
  description = "Owner IP address for SSH firewall rule. CIDR format. e.g. '1.2.3.4/32'."
  type        = string
}
