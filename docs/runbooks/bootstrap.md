# CLIVE Bootstrap Runbook

Use this when standing CLIVE up from scratch on a freshly provisioned VM.
Prerequisites: Terraform applied, VM reachable via SSH, repo cloned locally.

---

## 1. Terraform state bucket

Hetzner Object Storage does not support state locking (D-086 — known constraint, accepted for single-operator use).

1. In the Hetzner console, create an Object Storage bucket named `clive-terraform-state`.
2. Create an access key scoped to that bucket. Save the key ID and secret.
3. Set values in `infrastructure/terraform/terraform.tfvars`:
   ```
   state_bucket_name       = "clive-terraform-state"
   state_access_key        = "<key id>"
   state_secret_key        = "<secret>"
   ```
4. Initialise the backend:
   ```
   cd infrastructure/terraform
   terraform init
   ```
5. Confirm: Terraform prints `Successfully configured the backend "s3"`.

> **Known constraint (D-086):** Hetzner Object Storage has no lock API. Concurrent `terraform apply` runs are unsafe. Only one operator should apply at a time.

---

## 2. Ansible vault password

The vault password is stored in the password manager under the entry **"Ansible Vault Password"**. There may be multiple similar entries — use the one that successfully decrypts:

```
ansible-vault view infrastructure/ansible/vault.yml --ask-vault-pass
```

Confirm: the decrypted file contains all required secrets:

- `POSTGRES_PASSWORD`
- `APP_DB_PASSWORD`
- `AUDIT_WRITER_PASSWORD`
- `MINIO_ROOT_USER`
- `MINIO_ROOT_PASSWORD`
- `TELEGRAM_BOT_TOKEN`
- `backup_s3_endpoint`
- `backup_s3_access_key`
- `backup_s3_secret_key`

If any are missing, add them now with `ansible-vault edit infrastructure/ansible/vault.yml --ask-vault-pass` before proceeding.

---

## 3. First Ansible playbook run

```
ansible-playbook -i infrastructure/ansible/inventory \
  infrastructure/ansible/playbook.yml \
  --ask-vault-pass
```

This runs all roles in order: base, docker, clive-secrets, compose-deploy, postgres-init, backup-cron, github-runner.

Confirm: output ends with `failed=0` for all hosts. Any `changed` tasks are expected on first run. Investigate any `failed` before continuing.

---

## 4. MinIO bucket creation

The `clive-raw` bucket must exist before:
- The first ingestion run (Block 14 uploads raw documents here — D-094 T9)
- The first backup run (backup-cron syncs from this bucket)

Block 14 will surface a clear error if the bucket is missing; it will not create it silently.

SSH to the VM, then:

```
source /etc/clive/secrets.env && \
docker exec clive-minio mc alias set local http://localhost:9000 \
  $MINIO_ROOT_USER $MINIO_ROOT_PASSWORD && \
docker exec clive-minio mc mb local/clive-raw
```

Confirm: `Bucket created successfully. \`local/clive-raw\``

> **Note:** this step is a v0.2 prerequisite — the ingestion pipeline (Block 14 + Block 15) will reject uploads with a clear error message if the bucket is absent.  Do not rely on error messages to discover this; complete this step before sending any `/ingest` commands.

---

## 5. System document seeding and activation

The seed container runs automatically at deploy time and inserts `personality` and `alignment_rules` documents with `is_active = false`. Both must be activated explicitly via Telegram before CLIVE responds with personality (D-079 — two-step activation).

**Activate personality:**

1. Send `/activate personality` to @clivesystem_bot
2. Review the preview — confirm it matches the approved Block 1 document
3. Send `/confirm_activate <version_id>` (version_id shown in the preview message)
4. Confirm: bot replies `Activated.`

**Activate alignment rules:**

1. Send `/activate alignment_rules` to @clivesystem_bot
2. Review the preview — confirm it matches the approved alignment document
3. Send `/confirm_activate <version_id>`
4. Confirm: bot replies `Activated.`

> **Note (D-079):** Activation is a two-step process by design. `/activate` shows the pending version; `/confirm_activate <version_id>` commits it. The version_id must match exactly — mismatches are rejected.

---

## 6. Verify backup

Trigger the backup manually to confirm rclone can reach MinIO on the container network and that the destination bucket is reachable:

```
docker compose -f /home/clive/compose/docker-compose.yml run --rm backup
```

Confirm:
- Output contains `There was nothing to transfer` or a list of transferred files
- No `ERROR` lines in output

If the backup fails, check `/var/log/clive/backup.log` for detail.

---

## 7. Pre-launch checklist

Complete every item in the pre-launch checklist in `CLAUDE.md` before declaring CLIVE operational. Send a test message to @clivesystem_bot and confirm a coherent response is returned.
