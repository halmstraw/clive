variable "hcloud_token" {
  description = "Hetzner Cloud API token"
  type        = string
  sensitive   = true
}

variable "ssh_public_key" {
  description = "Owner SSH public key content"
  type        = string
}

variable "owner_ip" {
  description = "Owner IP address for SSH firewall rule (without /32 suffix)"
  type        = string

  validation {
    condition     = can(regex("^(\\d{1,3}\\.){3}\\d{1,3}$", var.owner_ip))
    error_message = "owner_ip must be a plain IPv4 address with no /32 suffix (e.g. 1.2.3.4). Check the OWNER_IP GitHub Actions secret."
  }
}
