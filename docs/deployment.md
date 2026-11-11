# Deploying CliQ.

One server runs the whole platform with Docker Compose. Everything below has
been exercised end to end on a laptop with `PLATFORM_ROOT_DOMAIN=localhost`
(2026-11-12, see "Rehearse locally"); it has **not** yet been run on a public
server with real DNS and Let's Encrypt certificates.

## What runs

| Service | Role | Exposed |
|---|---|---|
| `caddy` | Reverse proxy, HTTPS (Let's Encrypt), compression, JSON access logs | 80, 443 |
| `storefront` | Every brand's shop (`<brand>.<root>` and verified custom domains) | via Caddy |
| `admin` | Merchant console + platform admin at `app.<root>/admin` | via Caddy |
| `api` | FastAPI backend; webhooks and `/media` at `api.<root>` | only webhooks, media, health |
| `migrate` | `alembic upgrade head`, runs to completion before `api` starts | — |
| `scheduler` | Periodic jobs: order expiry, shipment sync, Sheets export, cart expiry, review requests | — |
| `postgres`, `redis`, `minio` | Data, cache/rate limits, object storage (images) | internal only |
| `backup` | Nightly `pg_dump`, kept `BACKUP_KEEP_DAYS` days | — |

Hostnames, for `PLATFORM_ROOT_DOMAIN=cliq.example.com`:

- `app.cliq.example.com` — merchant sign-in, brand list, store settings; platform admin at `/admin/platform`
- `northwind.cliq.example.com` — a brand's store; custom domains (CNAME to that address) once verified
- `api.cliq.example.com` — payment and courier webhooks, uploaded media
- `media.cliq.example.com` — product images and direct uploads (bundled MinIO)
- `cliq.example.com` — redirects to `app.`

Storefront certificates are issued **on demand** the first time a host is
requested, and only after the API confirms it is a real, active store
(`GET /api/v1/internal/tls-allowed`). Unknown names get no certificate.

## Requirements

- A Linux server with Docker Engine 24+ and the Compose plugin; 4 GB RAM is the
  minimum, 8 GB recommended. Builds need ~2 GB free.
- DNS: `A` (and `AAAA` if you have IPv6) records for `<root>` **and** `*.<root>`
  pointing at the server.
- Ports 80 and 443 open (80 is needed for Let's Encrypt); everything else closed
  (e.g. `ufw allow 22,80,443/tcp && ufw allow 443/udp && ufw enable`).
- Database connections: each API worker may open `DB_POOL_SIZE + DB_MAX_OVERFLOW`
  (default 20). Keep `API_WORKERS × 20 + 40` (scheduler, AI worker, migrate,
  backups) under PostgreSQL's default `max_connections` of 100. So with the default
  pool, use at most 3 workers. For more, lower `DB_POOL_SIZE`/`DB_MAX_OVERFLOW`
  (e.g. 5/5 for 6 workers).
- Let's Encrypt issues at most 50 new certificates per registered domain per week.
  Each new brand subdomain uses one; renewals don't count. Beyond ~50 new brands a
  week, switch to a wildcard certificate (DNS challenge; needs a Caddy build with
  your DNS provider's module), which is not set up here.
- Container logs are capped at 5 × 20 MB per service (`x-logging`).

## First deploy

```sh
git clone <repo> cliq && cd cliq
cp .env.production.example .env.production
# Fill in every CHANGE_ME. Secrets: openssl rand -hex 32
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
docker compose -f docker-compose.prod.yml --env-file .env.production ps     # all healthy?

# Create the operator's own store and admin login (idempotent):
docker compose -f docker-compose.prod.yml --env-file .env.production \
    run --rm api python -m app.commands.bootstrap

# Make your merchant account a platform administrator (register it first at
# https://app.<root>/admin/register):
docker compose -f docker-compose.prod.yml --env-file .env.production \
    run --rm api python -m app.commands.platform_admin grant you@example.com
```

Then, at the providers (when you have accounts):

- Razorpay (the platform's account), two webhooks:
  - payments for your own store: `https://api.<root>/api/v1/payments/razorpay/webhook` —
    events `payment.captured`, `order.paid`, `refund.processed`, `refund.failed`; secret = `RAZORPAY_WEBHOOK_SECRET`
  - plan billing: `https://api.<root>/api/v1/billing/razorpay/webhook` — events
    `subscription.activated`, `subscription.charged`, `subscription.pending`, `subscription.halted`,
    `subscription.cancelled`, `subscription.completed`, `subscription.resumed`;
    secret = `RAZORPAY_BILLING_WEBHOOK_SECRET` (or the same secret). Enable **Subscriptions** on the account.
- Every other brand connects **its own** Razorpay account in its console
  (Integrations → Online payments); the console shows the brand its webhook URL.
- SMTP: set `SMTP_*` and `EMAIL_FROM_ADDRESS` on a domain with SPF and DKIM configured at your provider
  (Gmail: `smtp.gmail.com`, 587, `starttls`, an App Password; see `.env.production.example`). Then:
  ```sh
  $C run --rm api python -m app.commands.smtp_check                 # STARTTLS + login only
  $C run --rm api python -m app.commands.smtp_check --to you@example.com
  ```
  How sending works: emails are written to the `email_outbox` table in the same transaction as the event
  and sent by the scheduler's `emails` job (every 30 s, one SMTP connection per batch, 20 s timeout).
  - If the provider is down or login/TLS fails, emails stay queued, the job shows failed in the System tab, and the alert webhook fires.
  - A permanently rejected address (5xx) fails that one email.
  - Transient errors retry with backoff up to `EMAIL_MAX_ATTEMPTS`.
  - The API never waits on SMTP.
- Shiprocket tracking webhook: `https://api.<root>/api/v1/courier-webhooks/tracking`, token = `SHIPROCKET_WEBHOOK_TOKEN`

## Updating (deploy procedure)

```sh
cd cliq
# 1. Take a backup first (in addition to the nightly one).
docker compose -f docker-compose.prod.yml --env-file .env.production exec backup sh /usr/local/bin/backup.sh
# 2. Get the new code and bump CLIQ_VERSION in .env.production (e.g. 7 -> 8).
git pull
# 3. Build and roll out. `migrate` runs first; the API is only replaced if it succeeds.
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
docker compose -f docker-compose.prod.yml --env-file .env.production ps
docker compose -f docker-compose.prod.yml --env-file .env.production logs --tail=50 migrate api
```

Migrations are written to be additive (new tables/columns, backfills). Never run
`alembic downgrade` or a database reset against production data.

## Rolling back

- **Code only (no migration in the release):** set `CLIQ_VERSION` back to the
  previous number and `up -d` again — the previous images are still on disk.
- **The release included a migration:** the old code usually still works with the
  newer (additive) schema, so roll back code as above. `migrate` sees a database
  newer than the code, logs `"status": "skipped"` and lets the old API start
  (verified on the rehearsal stack). If it does not, restore the
  backup taken in step 1 (below) and then roll back code. Restoring loses orders
  placed since the backup, so prefer a fix-forward release when possible.

## Backups and restore

- `backup` writes `cliq-<UTC time>.dump` to the `backups` volume every
  `BACKUP_INTERVAL_SECONDS` (default daily) and deletes dumps older than
  `BACKUP_KEEP_DAYS`. A dump is only kept if `pg_restore --list` reads it back.
- **Copy dumps off the server.** A volume on the same disk is not a backup against
  losing the server. For example, a nightly cron on the host:

  ```sh
  docker run --rm -v cliq_backups:/b alpine tar -C /b -cf - . | \
      ssh backup@elsewhere 'cat > cliq-backups-$(date +%F).tar'
  ```

  or `rclone copy` to S3/B2 with a bucket lifecycle rule.
- Uploaded images live in the `minio_data` volume (or your S3 bucket). Back that up
  too (`mc mirror`, or the provider's versioning).
- **Restore drill (do it monthly):**

  ```sh
  docker run --rm -v cliq_backups:/b -v "$PWD":/out alpine \
      sh -c 'cp "$(ls -t /b/cliq-*.dump | head -1)" /out/latest.dump'
  deploy/backup/restore-drill.sh latest.dump
  ```

  It restores into a throwaway PostgreSQL with no network, prints the migration
  version and row counts, checks order totals, and exits non-zero on any problem.
- **Real restore** (after stopping traffic):

  ```sh
  docker compose -f docker-compose.prod.yml --env-file .env.production stop api scheduler ai-worker storefront admin
  # Single quotes: the user and database names come from the container's environment.
  docker compose -f docker-compose.prod.yml --env-file .env.production exec -T postgres \
      sh -c 'pg_restore --clean --if-exists --no-owner -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < latest.dump
  docker compose -f docker-compose.prod.yml --env-file .env.production up -d
  ```

  Verified on the rehearsal stack (2026-11-12): fresh dump → restore → same row
  counts, stack healthy. Stored brand payment keys are encrypted with
  `SECRETS_ENCRYPTION_KEY`: a restore onto a server with a different key loses them
  (brands must re-enter them), so keep that key with your backups, stored separately.

## Monitoring

- **Health:** every service has a Docker health check (`docker compose ps`) and
  `restart: unless-stopped`. Point an uptime monitor (UptimeRobot, Better Stack, …)
  at `https://api.<root>/health/ready` (database + Redis) and at one storefront URL.
- **Logs:** the API, scheduler, backup job and Caddy write one JSON object per
  line; API lines carry `request_id` (also returned to clients as `X-Request-Id`),
  `path`, `status`, `duration_ms` and `host`. Server errors in the storefront and
  console are JSON lines with `"logger": "next"`.
  `docker compose logs -f api | grep '"level": "error"'`
- **Errors:** set `SENTRY_DSN` (sentry.io, or self-hosted Sentry/GlitchTip) and
  unhandled API and job errors are reported with their request id and release
  (`CLIQ_VERSION`). Cookies, auth headers, cart tokens and request bodies are
  never sent.
- **Alerts:** set `ALERT_WEBHOOK_URL` to a Slack, Discord or Google Chat incoming
  webhook. A failing background job, or less than `DISK_ALERT_FREE_PERCENT` disk
  free, posts one message per problem per hour.
- **Operator view:** `https://app.<root>/admin/platform` → **System** shows the
  database and Redis, each background job's last run and last success, and
  which provider credentials are still missing.

## Rehearse locally

The same stack runs on a laptop with Caddy's own certificate authority:

```sh
cp .env.production.example .env.prodtest
# PLATFORM_ROOT_DOMAIN=localhost, CADDY_EXTRA_GLOBAL_OPTIONS=local_certs,
# STOREFRONT_URL_TEMPLATE=https://{subdomain}.{root}, random secrets, SEED_ADMIN_PHONE
P="-p cliq-prodtest -f docker-compose.prod.yml --env-file .env.prodtest"
CLIQ_ENV_FILE=.env.prodtest docker compose $P up -d --build --wait
CLIQ_ENV_FILE=.env.prodtest docker compose $P run --rm api python -m app.commands.bootstrap
# Product photos are resized by the storefront, which must trust Caddy's local CA:
docker cp cliq-prodtest-caddy-1:/data/caddy/pki/authorities/local/root.crt deploy/.rehearsal-ca.crt
CLIQ_ENV_FILE=.env.prodtest docker compose $P -f deploy/rehearsal.override.yml up -d --wait storefront
curl -k https://app.localhost/admin/signin
```

Rehearsal results (2026-11-12): every service healthy; migrations ran before
the API; bootstrap store live at `https://<slug>.localhost`; a brand created in
the console got its certificate on first visit, an unknown name got none;
private API routes 404 from outside; all scheduler jobs ran; backup + restore
drill passed on real data; E2E 4/4 over HTTPS; load (laptop, 2 API workers,
through Caddy/TLS): 25 shoppers 111 req/s p95 445 ms, 60 shoppers 121 req/s
p95 919 ms, 0 errors. Throughput is bound by API CPU: raise `API_WORKERS`
(≈ one per core) on a bigger server.

Browsers resolve `*.localhost` to your machine; accept the local certificate (or
trust Caddy's root CA from the `caddy_data` volume).

## Environments

- **Production:** `.env.production` (`ENVIRONMENT=production`; the API refuses to
  start with weak JWT secrets, `CORS_ORIGINS=*` or the mock AI provider).
- **Staging:** a second server (or compose project) with its own
  `.env.staging`, its own domain (e.g. `staging-cliq.example.com`), Razorpay test
  keys and `ENVIRONMENT=staging`. Never point staging at production's database.
- **Development:** `docker-compose.yml` + `npm run dev` in each frontend (README).
