# CLIVE Day-2 Operations Runbook

**Owner:** Block 29 (Documentation)
**Decision:** D-076, D-090

Day-to-day operational reference for a running CLIVE instance.
For initial setup see `docs/runbooks/bootstrap.md` and `docs/runbooks/terraform-bootstrap.md`.

---

## SSH Access

```bash
ssh -i ~/.ssh/clive_vm root@138.199.149.201
```

The VM IP is `138.199.149.201`. The private key is `~/.ssh/clive_vm`.
If the IP changes after a Terraform apply, update this file.

---

## Check Service Status

```bash
docker ps
```

All six containers should show `Up` and `healthy`:
- `clive-orchestrator`
- `clive-processing`
- `clive-query`
- `clive-telegram`
- `clive-postgres`
- `clive-minio`

---

## View Logs

```bash
# Live-follow a service
docker logs -f clive-processing
docker logs -f clive-orchestrator
docker logs -f clive-query
docker logs -f clive-telegram

# Last 50 lines
docker logs clive-processing --tail 50
```

---

## Restart a Service

```bash
docker restart clive-processing
docker restart clive-orchestrator
docker restart clive-query
docker restart clive-telegram
```

---

## Add or Update a Secret

Secrets live in `/etc/clive/secrets.env`. There are two ways to update them:

### Immediate (takes effect on next container restart)

```bash
# Edit directly on the server
nano /etc/clive/secrets.env

# Then restart the affected service
docker restart clive-processing
```

### Permanent (survives Ansible re-runs — always do this too)

On your local machine:

```bash
ansible-vault edit infrastructure/ansible/vault.yml --ask-vault-pass
```

Add or update the variable (snake_case), for example:
```yaml
openai_api_key: sk-...
```

Then commit and push. The next Ansible run will write the updated `secrets.env`.

**Required secrets as of v0.2:**

| Secret | Purpose |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Telegram bot authentication |
| `TELEGRAM_OWNER_CHAT_ID` | Owner's Telegram chat ID |
| `ANTHROPIC_API_KEY` | LLM calls via LiteLLM (query service) |
| `OPENAI_API_KEY` | Embeddings via text-embedding-3-small (processing service) |
| `POSTGRES_PASSWORD` | PostgreSQL superuser password |
| `APP_DB_PASSWORD` | `clive_app` role password |
| `AUDIT_WRITER_PASSWORD` | `clive_audit_writer` role password |
| `MINIO_ROOT_USER` | MinIO root credentials |
| `MINIO_ROOT_PASSWORD` | MinIO root credentials |

---

## Apply a Database Migration Manually

If a migration needs to be applied outside of a deploy:

```bash
docker exec -i clive-postgres psql -U postgres -d clive << 'EOF'
-- paste migration SQL here
EOF
```

Or to apply a specific file from the checked-out repo:

```bash
PGPASSWORD=$(grep '^POSTGRES_PASSWORD=' /etc/clive/secrets.env | cut -d= -f2 | tr -d '\r')
docker exec -e PGPASSWORD="$PGPASSWORD" -i clive-postgres \
  psql -U postgres -d clive < /path/to/migration.sql
```

---

## Inspect the MinIO Bucket

```bash
MINIO_ROOT_USER=$(grep '^MINIO_ROOT_USER=' /etc/clive/secrets.env | cut -d= -f2 | tr -d '\r')
MINIO_ROOT_PASSWORD=$(grep '^MINIO_ROOT_PASSWORD=' /etc/clive/secrets.env | cut -d= -f2 | tr -d '\r')

# List objects in clive-raw-store
docker run --rm \
  --network container:clive-minio \
  -e MC_HOST_local="http://${MINIO_ROOT_USER}:${MINIO_ROOT_PASSWORD}@localhost:9000" \
  minio/mc ls local/clive-raw-store

# Create bucket if missing
docker run --rm \
  --network container:clive-minio \
  -e MC_HOST_local="http://${MINIO_ROOT_USER}:${MINIO_ROOT_PASSWORD}@localhost:9000" \
  minio/mc mb --ignore-existing local/clive-raw-store
```

---

## Query the Audit Log

```bash
PGPASSWORD=$(grep '^POSTGRES_PASSWORD=' /etc/clive/secrets.env | cut -d= -f2 | tr -d '\r')
docker exec -e PGPASSWORD="$PGPASSWORD" -i clive-postgres \
  psql -U postgres -d clive -c \
  "SELECT event_type, timestamp, routing_outcome FROM clive_audit.event_log ORDER BY timestamp DESC LIMIT 20;"
```

---

## Check Ingested Chunks

```bash
PGPASSWORD=$(grep '^POSTGRES_PASSWORD=' /etc/clive/secrets.env | cut -d= -f2 | tr -d '\r')
docker exec -e PGPASSWORD="$PGPASSWORD" -i clive-postgres \
  psql -U postgres -d clive -c \
  "SELECT source_key, count(*) FROM clive_search.chunks GROUP BY source_key ORDER BY count DESC;"
```

---

## Trigger Manual Backup

```bash
docker compose -f /home/clive/compose/docker-compose.yml run --rm backup
```

---

## Disk Usage

```bash
df -h /
docker system df
```

---

## Re-run Ansible (full config refresh)

From your local machine:

```bash
ansible-playbook -i infrastructure/ansible/inventory \
  infrastructure/ansible/playbook.yml \
  --ask-vault-pass
```

This re-writes `/etc/clive/secrets.env` from the vault, re-creates the MinIO bucket
(idempotent), and re-applies any role changes.
