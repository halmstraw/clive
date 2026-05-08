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
  description = "Owner IP address for SSH firewall rule (without /32)"
  type        = string
}
