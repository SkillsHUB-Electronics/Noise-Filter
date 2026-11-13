# Sample intake Worker (F3)

Receives opt-in noise samples from the app and stores them in the Cloudflare R2 bucket `nf-noise`.

| Route | What it does |
|---|---|
| `POST /v1/samples` | WAV body (48 kHz, mono, 16-bit PCM, 2-10 s, max 2 MB) + header `X-NF-Meta` JSON `{install_id, category, app_version, os, consent: "cc0-v1"}`. Stored at `incoming/<install_id>/<date>-<uuid>.wav`. |
| `DELETE /v1/samples?install_id=…` | Deletes every sample of that installation (incoming, accepted, rejected). |
| `GET /v1/health` | Liveness check. |

Categories: `fan_ac`, `traffic`, `keyboard`, `crowd`, `machine`, `rain_wind`, `other`.

The Worker stores no IP address. It never decides what is used for training: CI screens
`incoming/` again (speech, duplicates, clipping, silence) and moves samples to `accepted/` or `rejected/`.

## Tests

    npm test        # Node 22, no dependencies

## Deploy

GitHub Actions (`.github/workflows/worker.yml`) deploys from the default branch when the
repository secrets `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` exist. Before that:

1. Create the R2 bucket `nf-noise` in the Cloudflare dashboard.
2. Create an API token with **Workers Scripts: Edit** and **Workers R2 Storage: Edit**.
3. Add both secrets in GitHub → Settings → Secrets and variables → Actions.

The Worker is then served at `https://noise-filter-samples.<your-subdomain>.workers.dev`.
