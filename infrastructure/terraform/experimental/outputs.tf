# Block 24 — Experimental environment outputs (v1.0, D-152)
# These outputs are consumed by Block 21 (Evolution Engine) via the controlled
# event bridge (D-024) to route events to the correct experimental host.

output "server_id" {
  description = "Hetzner server ID of the experimental VM."
  value       = hcloud_server.experimental.id
}

output "server_ip" {
  description = "Public IPv4 address of the experimental VM. Used by Block 21 to route events and SSH for setup."
  value       = hcloud_server.experimental.ipv4_address
}

output "experiment_name" {
  description = "The experiment name used to label all resources in this environment."
  value       = var.experiment_name
}

output "firewall_id" {
  description = "Hetzner firewall ID. Referenced when tightening rules post-provisioning."
  value       = hcloud_firewall.experimental.id
}
