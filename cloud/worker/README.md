# Sample intake Worker (F3)

Receives opt-in noise samples from the app and stores them in the Cloudflare R2 bucket `nf-noise`.

| Route | What it does |
|---|---|
| `POST /v1/samples` | WAV body (48 kHz, mono, 16-bit PCM, 2-10 s, max 2 MB) + header `X-NF-Meta` JSON `{install_id, category, app_version, os, consent: "cc0-v1", source: "mic"\|"file"}`. Stored at `incoming/<install_id>/<date>-<uuid>.wav`. |
| `DELETE /v1/samples?install_id=…` | Deletes every sample of that installation (incoming, review, accepted, rejected). |
| `GET /v1/health` | Liveness check. |
| `GET /review` | Developer review page (listen, spectrogram, accept/reject, keyboard shortcuts). |
| `GET /v1/review/list?state=…`, `/audio?key=…`, `/stats`, `POST /v1/review/decide` | Review API, needs `Authorization: Bearer <REVIEW_PASSWORD>`. |

Categories: `fan_ac`, `traffic`, `keyboard`, `crowd`, `machine`, `rain_wind`, `other`.

The Worker stores no IP address. It never decides what is used for training:

    incoming/ --daily CI check (speech, duplicates, clipping, silence, daily cap)--> review/ or rejected/
    review/   --developer on /review--> accepted/ (used for training) or rejected/ (deleted after 30 days)

Samples that were accepted automatically before the review step existed go back to `review/` on the next CI run.

## Review page

1. Add the GitHub secret `REVIEW_PASSWORD` (at least 12 characters; a long random phrase is best).
2. Run the "Sample intake Worker" workflow once (Actions → Run workflow) so it stores the password in the Worker.
3. Open `https://noise-filter-samples.mukhamadkhoirul.workers.dev/review` and log in.

Shortcuts: Space play/pause, A accept, R reject, U back to the queue, Z undo, ↓/J and ↑/K to move. A wrong password
is limited to 5 tries a minute.

## Tests

    npm test        # Node 22, no dependencies

## Deploy

GitHub Actions (`.github/workflows/worker.yml`) deploys from the default branch when the
repository secrets `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` exist. Before that:

1. Create the R2 bucket `nf-noise` in the Cloudflare dashboard.
2. Create an API token with **Workers Scripts: Edit** and **Workers R2 Storage: Edit**.
3. Add both secrets in GitHub → Settings → Secrets and variables → Actions.

The Worker is then served at `https://noise-filter-samples.<your-subdomain>.workers.dev`.
