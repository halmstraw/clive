# Terraform State Bootstrap Runbook

**Owner:** Block 29 (Documentation)
**Required before:** First `terraform apply`
**Decision:** D-076

## Overview

Terraform state for CLIVE is stored remotely in a Hetzner S3-compatible object
storage bucket. This bucket cannot be managed by Terraform itself — it must exist
before Terraform is initialised. This is a one-time manual bootstrap step.

## Prerequisites

- Hetzner Cloud account with API access
- Hetzner Object Storage enabled on the account
- `terraform` CLI installed (>= 1.6)
- AWS CLI or `s3cmd` for bucket creation (Hetzner Object Storage is S3-compatible)

## Steps

### 1. Create the state bucket

Log in to the Hetzner Cloud console and navigate to Object Storage.
Create a new bucket named `clive-terraform-state` in the `fsn1` region.

Or via AWS CLI with Hetzner endpoint:

```
aws s3 mb s3://clive-terraform-state \
  --endpoint-url https://fsn1.your-objectstorage.com \
  --region main
```

### 2. Create access credentials

In the Hetzner Cloud console, create an Object Storage access key pair.
Save the access key ID and secret access key securely — you will need them
for Terraform and for GitHub Actions secrets.

### 3. Configure environment variables for Terraform

```
export AWS_ACCESS_KEY_ID=<your-access-key-id>
export AWS_SECRET_ACCESS_KEY=<your-secret-access-key>
```

### 4. Initialise Terraform

```
cd infrastructure/terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values
terraform init
```

Expected output includes: `Successfully configured the backend "s3"!`

### 5. Verify state locking

```
terraform plan
```

If state locking is working, you will see: `Acquiring state lock.`
If the bucket does not exist or credentials are wrong, Terraform will error
before making any changes.

### 6. Add secrets to GitHub Actions

In the repository Settings → Secrets and variables → Actions, add:

| Secret name | Value |
|---|---|
| `HCLOUD_TOKEN` | Hetzner Cloud API token |
| `CLIVE_SSH_PRIVATE_KEY` | Private key matching the public key in terraform.tfvars |
| `CLIVE_SSH_PUBLIC_KEY` | SSH public key |
| `OWNER_IP` | Your IP address for SSH firewall rule |
| `TF_STATE_ACCESS_KEY` | Object Storage access key ID (from step 2) |
| `TF_STATE_SECRET_KEY` | Object Storage secret access key (from step 2) |
| `ANSIBLE_VAULT_PASSWORD` | Password for ansible-vault encrypted vault.yml |
| `CLIVE_SERVER_IP` | VM IP — available after first terraform apply |

**Note:** `CLIVE_SERVER_IP` is only available after the first `terraform apply`.
Add it after the VM is created.

### 7. First deploy

```
terraform apply
```

After apply completes, copy the output `clive_server_ip` value and add it as
the `CLIVE_SERVER_IP` GitHub Actions secret.

## Recovery

If the state bucket is lost:
1. Re-create the bucket with the same name
2. Restore from the most recent Hetzner VM snapshot (which includes the state
   bucket contents if backed up) or treat it as a fresh deployment
3. Run `terraform import` for any existing resources before applying

## Verification checklist

- [ ] `clive-terraform-state` bucket exists in Hetzner Object Storage
- [ ] AWS credentials for bucket access are saved securely
- [ ] `terraform init` completes without error
- [ ] `terraform plan` shows state lock acquired
- [ ] All GitHub Actions secrets populated
- [ ] First `terraform apply` completes and VM IP is recorded
