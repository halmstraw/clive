output "clive_server_ip" {
  description = "Public IP address of the CLIVE VM — use in Ansible inventory"
  value       = hcloud_server.clive.ipv4_address
}

output "clive_server_id" {
  description = "Hetzner server ID"
  value       = hcloud_server.clive.id
}
