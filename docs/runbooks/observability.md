# CLIVE Observability Runbook

**Owner:** Block 29 (Documentation)
**Decisions:** D-117, D-118, D-121

The observability stack collects metrics from every service and the host VM, aggregates all container logs, evaluates alert rules, and routes firing alerts through the orchestrator webhook into Block 13's event bus, which delivers them to the owner's Telegram chat. Grafana is publicly accessible at `https://grafana.halmshaw.co.uk` via Caddy reverse proxy with Google OAuth authentication (D-121).

---

## Accessing Grafana

Open `https://grafana.halmshaw.co.uk` in a browser and sign in with Google. Only accounts with a `gmail.com` domain are permitted (`GF_AUTH_GOOGLE_ALLOWED_DOMAINS=gmail.com`). Self-registration is disabled.

**DNS prerequisite:** An A record for `grafana.halmshaw.co.uk` must point to `138.199.149.201` before the TLS certificate can be issued by Caddy. If the cert is not yet provisioned, Caddy will attempt ACME challenge on port 80 automatically — no manual step required once DNS resolves.

**Fallback — admin username/password:** The local Grafana admin account remains active. If Google OAuth is not yet configured or is unavailable, use the SSH tunnel method:

```bash
ssh -i ~/.ssh/clive_vm -L 3000:127.0.0.1:3000 root@138.199.149.201 -N
```

Then open `http://localhost:3000` in a browser. Login with username `admin` and the `GRAFANA_ADMIN_PASSWORD` from `/etc/clive/secrets.env`.

To retrieve the password from the VM:

```bash
ssh -i ~/.ssh/clive_vm root@138.199.149.201 \
  "grep '^GRAFANA_ADMIN_PASSWORD=' /etc/clive/secrets.env | cut -d= -f2 | tr -d '\r'"
```

---

## Google OAuth Setup (one-time owner step)

This must be completed before Google OAuth login works at `grafana.halmshaw.co.uk`.

1. Go to [Google Cloud Console](https://console.cloud.google.com/) and create a new OAuth 2.0 Client ID (type: Web application).
2. Set the authorised redirect URI to: `https://grafana.halmshaw.co.uk/login/google`
3. Copy the Client ID and Client Secret.
4. SSH into the VM and add the secrets to `/etc/clive/secrets.env`:

   ```bash
   ssh -i ~/.ssh/clive_vm root@138.199.149.201
   # Edit /etc/clive/secrets.env and add:
   # GOOGLE_CLIENT_ID=<your-client-id>
   # GOOGLE_CLIENT_SECRET=<your-client-secret>
   ```

   Or re-run the Ansible playbook with the values set in vault/vars.

5. Restart Grafana to pick up the new env vars:

   ```bash
   docker compose -f /home/clive/compose/docker-compose.yml restart grafana
   ```

6. Test login at `https://grafana.halmshaw.co.uk`.

---

## Dashboards

Dashboards are provisioned automatically from `infrastructure/observability/grafana/dashboards/` into the **CLIVE** folder in Grafana. UI edits are disabled — changes must go through the provisioning files.

| Dashboard | What it shows |
|---|---|
| `system_overview` | VM CPU usage, memory usage, disk usage, and per-container resource consumption (via cAdvisor and node-exporter) |

A `services` dashboard showing per-service HTTP request rates, error rates, and latency is planned for Phase 2, once the CLIVE application services expose `/metrics` endpoints. The alert rules for those metrics (`CliveHighErrorRate`) are already defined but will not fire until Phase 2.

---

## Querying Logs in Loki

Open Grafana, go to **Explore**, and select the **Loki** datasource.

Promtail ships all container logs to Loki. Logs are labelled by `compose_service` and `container_name` (parsed from the Docker log tag) and by `stream` (stdout/stderr).

**Useful LogQL queries:**

All logs for a specific service:

```logql
{compose_service="orchestrator"}
```

Error-level logs across all CLIVE containers:

```logql
{job="docker"} |= "ERROR"
```

Logs for a service containing a keyword:

```logql
{compose_service="query"} |= "retrieval"
```

Last 100 lines from a container by name:

```logql
{container_name="clive-telegram"}
```

Adjust the time range in Grafana's top-right picker. For live tailing, use the **Live** toggle.

---

## Alert Rules

Prometheus evaluates rules every 15 seconds. Firing alerts POST to `http://orchestrator:8080/alerts` via the Grafana contact point `CLIVE Orchestrator`. The orchestrator publishes the alert onto the Block 13 event bus; Block 4 (Interface/Egress) routes it to the owner's Telegram chat (D-118).

**System alerts** (`infrastructure/observability/prometheus/rules/system.yml`):

| Alert | Fires when | Severity |
|---|---|---|
| `DiskSpaceLow` | Root filesystem usage exceeds 80% for 5 minutes | warning |
| `MemoryUsageHigh` | VM memory usage exceeds 85% for 5 minutes | warning |
| `NodeExporterDown` | node-exporter unreachable for 2 minutes | critical |

**Service alerts** (`infrastructure/observability/prometheus/rules/services.yml`):

| Alert | Fires when | Severity |
|---|---|---|
| `CliveServiceDown` | orchestrator, query, telegram, or processing unreachable for 2 minutes | critical |
| `ContainerRestartLoop` | any `clive-*` container restarts more than 3 times in 15 minutes | warning |
| `CliveHighErrorRate` | more than 5% of requests to a service return 5xx over 5 minutes | warning |

`CliveHighErrorRate` requires Phase 2 `/metrics` endpoints on the application services. It will not fire until those are added.

---

## Checking Prometheus Directly

Prometheus has no authentication and is bound to the internal Docker network only. Port-forward to inspect it:

```bash
ssh -i ~/.ssh/clive_vm -L 9090:clive-prometheus:9090 root@138.199.149.201 -N
```

Then open `http://localhost:9090` in a browser.

**Check scrape targets** (all should show State: UP):

`http://localhost:9090/targets`

**Example PromQL query** — current memory usage percentage:

```promql
1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)
```

Prometheus retains 30 days of data.

---

## Service Health

All long-running containers should show `Up` and `healthy`:

```bash
docker ps
```

Expected containers:

| Container | Role |
|---|---|
| `clive-orchestrator` | Block 13 — Central Orchestrator / event bus |
| `clive-processing` | Block 15 — Ingestion processing and embeddings |
| `clive-query` | Block 8 — Query / RAG |
| `clive-telegram` | Block 23 — Telegram surface |
| `clive-postgres` | Block 16 — PostgreSQL (search + state + audit) |
| `clive-minio` | Block 16 — MinIO object store |
| `clive-prometheus` | Block 25 — Metrics collection and alert evaluation |
| `clive-loki` | Block 25 — Log aggregation |
| `clive-promtail` | Block 25 — Log shipper |
| `clive-grafana` | Block 25 — Dashboards and alert dispatch |
| `clive-caddy` | Block 25 — Reverse proxy and TLS termination (D-121) |
| `clive-node-exporter` | Block 25 — VM host metrics |
| `clive-postgres-exporter` | Block 25 — PostgreSQL metrics |
| `clive-cadvisor` | Block 25 — Per-container metrics |

`clive-seed` and `clive-backup` are one-shot containers (`restart: "no"`) and will not appear in `docker ps` after they complete.

---

## Troubleshooting

**Observability containers not running:**

```bash
docker ps -a --filter "name=clive-prometheus"
docker ps -a --filter "name=clive-loki"
docker ps -a --filter "name=clive-grafana"
docker ps -a --filter "name=clive-caddy"
```

Check why a container exited:

```bash
docker logs clive-prometheus --tail 50
docker logs clive-loki --tail 50
docker logs clive-caddy --tail 50
```

**Restart an observability container:**

```bash
docker restart clive-prometheus
docker restart clive-loki
docker restart clive-promtail
docker restart clive-grafana
docker restart clive-caddy
```

**TLS certificate not issued:**

Caddy issues certs automatically on first request. If the cert is not present:

1. Confirm the DNS A record for `grafana.halmshaw.co.uk` resolves to `138.199.149.201`.
2. Confirm ports 80 and 443 are open in the Hetzner firewall (`terraform apply` may be needed).
3. Check Caddy logs: `docker logs clive-caddy --tail 100`

**Google OAuth login failing:**

1. Confirm `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are present in `/etc/clive/secrets.env`.
2. Confirm the authorised redirect URI in Google Cloud Console includes `https://grafana.halmshaw.co.uk/login/google`.
3. Restart Grafana: `docker compose -f /home/clive/compose/docker-compose.yml restart grafana`

**Check Prometheus scrape targets:**

Open `http://localhost:9090/targets` via the port-forward described above. Any target showing State: DOWN means Prometheus cannot reach that service. Check whether the container is running and on the `clive-internal` network.

**Check Loki is receiving logs:**

In Grafana Explore (Loki datasource), run:

```logql
{job="docker"}
```

If no results appear for the last 5 minutes, Promtail may have stopped shipping. Check:

```bash
docker logs clive-promtail --tail 50
```

A common cause is the Docker socket or container log path becoming inaccessible after a host reboot. Restart Promtail to recover.

**Alerts not arriving in Telegram:**

1. Confirm Prometheus shows the alert as `FIRING` at `http://localhost:9090/alerts`.
2. Confirm the orchestrator is healthy: `docker logs clive-orchestrator --tail 50`.
3. Confirm Grafana contact point is configured: **Alerting → Contact points** in Grafana UI should show `CLIVE Orchestrator` with the webhook URL `http://orchestrator:8080/alerts`.
