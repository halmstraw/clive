# Importing CLIVE dashboards into Grafana Cloud

The two JSON files in this directory are standard Grafana dashboard exports.
Import them into Grafana Cloud after the Alloy migration is complete.

**Files:**
- `system_overview.json` — VM, PostgreSQL, and service health metrics
- `event_bus.json` — Block 13 event throughput (D-134)

## Steps

1. Log in to Grafana Cloud at https://grafana.com and open your stack.

2. In the left sidebar: **Dashboards → New → Import**.

3. Click **Upload JSON file** and select `system_overview.json`.
   - When prompted for a data source, select your Grafana Cloud Prometheus source.
   - Click **Import**.

4. Repeat for `event_bus.json`.

5. If the panels show "No data", confirm that Alloy is running and that
   `GRAFANA_CLOUD_PROMETHEUS_URL` and `GRAFANA_CLOUD_API_KEY` are populated
   in `/etc/clive/secrets.env` on the VM.

## Alert routing (D-118)

After importing dashboards, configure the alert contact point so that alerts
route to the orchestrator webhook rather than directly to Telegram.

See the comment block at the top of
`infrastructure/observability/alloy/config.alloy` for the full step-by-step
instructions (Caddy route + Grafana Cloud contact point configuration).
