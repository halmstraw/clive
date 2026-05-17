# CLIVE — Experimental Environment IaC

Block 24 sandboxing stub / Block 21 Evolution Engine substrate (D-152, D-029).

This directory provisions an isolated experimental VM on Hetzner. It is **not
deployed by default**. Apply manually when activating an experiment.

---

## Prerequisites

- Hetzner Cloud account (separate API token from production — D-022)
- Hetzner Object Storage access key (for Terraform state)
- Your public SSH key
- Your current public IP (for firewall rule)

---

## Initialise per experiment

Each experimental environment uses a separate Terraform state key:

```bash
terraform init \
  -backend-config="key=experimental/<experiment-name>/terraform.tfstate" \
  -backend-config="access_key=<HETZNER_OBJ_ACCESS_KEY>" \
  -backend-config="secret_key=<HETZNER_OBJ_SECRET_KEY>"
```

Replace `<experiment-name>` with a unique lowercase identifier e.g. `exp-001`.

---

## Apply

```bash
terraform plan \
  -var="hcloud_token=<EXPERIMENTAL_HCLOUD_TOKEN>" \
  -var="ssh_public_key=$(cat ~/.ssh/id_ed25519.pub)" \
  -var="experiment_name=exp-001" \
  -var="owner_ip=$(curl -s ifconfig.me)/32"

terraform apply \
  -var="hcloud_token=<EXPERIMENTAL_HCLOUD_TOKEN>" \
  -var="ssh_public_key=$(cat ~/.ssh/id_ed25519.pub)" \
  -var="experiment_name=exp-001" \
  -var="owner_ip=$(curl -s ifconfig.me)/32"
```

Note the output `server_ip` — this is the host Block 21 routes events to.

---

## Destroy when done

Experimental environments are ephemeral. Always destroy when an experiment
completes to avoid ongoing cost:

```bash
terraform destroy \
  -var="hcloud_token=<EXPERIMENTAL_HCLOUD_TOKEN>" \
  -var="ssh_public_key=$(cat ~/.ssh/id_ed25519.pub)" \
  -var="experiment_name=exp-001" \
  -var="owner_ip=$(curl -s ifconfig.me)/32"
```

---

## Design constraints

- **D-022**: Experimental environments are isolated from production. Never use
  production credentials here. The experimental `hcloud_token` is a separate
  API token scoped to a separate Hetzner project.
- **D-024**: All communication between production and experimental environments
  routes through the controlled event bridge in Block 13. No direct DB or
  service access between environments.
- **D-029**: Block 21 uses these parameterised templates. It never modifies
  the templates themselves — it only applies them with different variable values.
- **D-034**: Every variant promotion from experimental to production requires
  explicit owner sign-off.

---

*Maintained alongside the project. Update via recorded decision only.*
