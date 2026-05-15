# CLIVE Day-2 Operations Runbook

**Owner:** Block 29 (Documentation)
**Decision:** D-076, D-090

Day-to-day operational reference for a running CLIVE instance.
For initial setup see `docs/runbooks/bootstrap.md` and `docs/runbooks/terraform-bootstrap.md`.
For observability (Grafana, Prometheus, Loki) see `docs/runbooks/observability.md`.

---

## SSH Access

```bash
ssh -i ~/.ssh/clive_vm_ed25519 root@138.199.149.201
```

The VM IP is `138.199.149.201`. The private key is `~/.ssh/clive_vm_ed25519`.
If the IP changes after a Terraform apply, update this file.

---

## Check Service Status

```bash
docker ps
```

All 12 long-running containers should show `Up` and `healthy`:
- `clive-orchestrator`
- `clive-processing`
- `clive-query`
- `clive-telegram`
- `clive-postgres`
- `clive-minio`
- `clive-prometheus`
- `clive-loki`
- `clive-promtail`
- `clive-grafana`
- `clive-node-exporter`
- `clive-postgres-exporter`

`clive-seed` and `clive-backup` are one-shot containers and will not appear after they complete.

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

**GitHub Actions secrets are the source of truth for CD deployments.**
`/etc/clive/secrets.env` is written by the deploy pipeline on every push to main.
Never edit it directly on the server — it will be overwritten on the next deploy.

To add or update a secret:
1. Go to GitHub → Settings → Secrets and variables → Actions
2. Add or update the secret value
3. Push any commit to main — the deploy pipeline will write the updated `secrets.env`
   and restart services automatically

**Required GitHub Actions secrets as of v0.2:**

| Secret name | Purpose |
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

The Ansible vault (`infrastructure/ansible/vault.yml`) retains these values
for bootstrapping new VMs. Keep it in sync when secrets change.

---

## Apply a Database Migration Manually

Migrations run automatically on every deploy. Only use this if you need to apply
one outside of a normal deploy cycle.

```bash
# SSH to server first
ssh -i ~/.ssh/clive_vm root@138.199.149.201

PGPASSWORD=$(grep '^POSTGRES_PASSWORD=' /etc/clive/secrets.env | cut -d= -f2 | tr -d '\r')
docker exec -e PGPASSWORD="$PGPASSWORD" -i clive-postgres \
  psql -U postgres -d clive << 'EOF'
-- paste migration SQL here
EOF
```

---

## Inspect the MinIO Bucket

```bash
# SSH to server first
ssh -i ~/.ssh/clive_vm root@138.199.149.201

MINIO_ROOT_USER=$(grep '^MINIO_ROOT_USER=' /etc/clive/secrets.env | cut -d= -f2 | tr -d '\r')
MINIO_ROOT_PASSWORD=$(grep '^MINIO_ROOT_PASSWORD=' /etc/clive/secrets.env | cut -d= -f2 | tr -d '\r')

# List objects in clive-raw-store
docker run --rm \
  --network container:clive-minio \
  -e MC_HOST_local="http://${MINIO_ROOT_USER}:${MINIO_ROOT_PASSWORD}@localhost:9000" \
  minio/mc ls local/clive-raw-store

# Create bucket if missing (deploy pipeline does this automatically)
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
