# CliQ. on Railway — runbook (deployed 2026-11-12)

Project **cliq** (`0d95c676-d518-4a10-a691-53c063624125`), environment
**production**, workspace plan **Hobby**. Deployed from commit `5745f2b`
(app code `a7d7907` + Railway fixes).

| URL | What |
|---|---|
| https://caddy-production-e45f33ac.up.railway.app | CliQ. storefront (+ webhooks, `/health/ready`, `/cliq-media/*`) |
| https://console-production-5a5a53ed.up.railway.app/admin/ | Merchant console + platform operator console (`/admin/platform`) |

## 1. Architecture

```
shopper ─▶ Railway edge (TLS) ─▶ caddy   ─┬─▶ storefront:3000 ──▶ api:8000
                                           ├─▶ api:8000   (webhooks, /health, /media only)
                                           └─▶ minio:9000 (POST /cliq-media, GET one object)
merchant ─▶ Railway edge (TLS) ─▶ console ─▶ admin:3001 ──▶ api:8000
api, scheduler, ai-worker, backup ─▶ Postgres 18, Redis, MinIO   (private network only)
```

| Service | Source | Public | Notes |
|---|---|---|---|
| caddy | `deploy/railway/caddy` | yes (store host) | routes by host/path; only public entry for shoppers |
| console | `deploy/railway/caddy` (same image) | yes (console host) | a Railway service gets one generated domain, so the console has its own ingress |
| api | `backend/` | no | 2 uvicorn workers; **pre-deploy: `python -m app.commands.migrate`** (runs once per deploy, skips when DB is newer) |
| scheduler | `backend/` | no | `python -m app.commands.scheduler`; 1 replica, `overlapSeconds 0` |
| ai-worker | `backend/` | no | Celery `-Q ai --concurrency=2`; 1 replica, `overlapSeconds 0`; idle until `AI_PROVIDER`/`FASHN_API_KEY` |
| storefront | `storefront-frontend/` | no | health check `/healthz` |
| admin | `admin-frontend/` | no | health check `/admin/signin` |
| minio | image `bitnamilegacy/minio:2025.5.24` | no | volume `/bitnami/minio/data`, `RAILWAY_RUN_UID=0` |
| Postgres / Redis | Railway templates | no | Postgres **18** (local dev and the self-hosted stack use 16) |
| backup | `deploy/railway/backup` | no | cron `30 20 * * *` UTC (02:00 IST), restart NEVER |

Config-as-code (`railway.json`) is deprecated by Railway (hard cutoff
2026-12-01), so service settings were applied with the CLI/API; this file is
the record. Internal hosts are Railway references (`${{api.RAILWAY_PRIVATE_DOMAIN}}`).

### Client IP (F1) on Railway — verified live

Railway's edge connects from `100.64.0.0/10` and sets `X-Real-IP` to the
client; it **appends** to `X-Forwarded-For` and **overwrites** client-sent
`X-Real-IP`/`X-Forwarded-For` (a spoofed `9.9.9.9` / `8.8.8.8` never reached
Caddy). Caddy trusts only `CADDY_TRUSTED_PROXIES=100.64.0.0/10`, reads
`X-Real-IP`, and sends exactly that address upstream. Without that variable
every shopper would share the edge's address (and its rate limits).
Re-check after any infrastructure change: send a spoofed header and read
`client_ip` in Caddy's JSON log (`railway logs -s caddy`).

## 2. Deploy / update / rollback

```sh
railway link -p 0d95c676-d518-4a10-a691-53c063624125      # once
railway up backend --path-as-root -s api -d                # migrations run in pre-deploy
railway up backend --path-as-root -s scheduler -d
railway up backend --path-as-root -s ai-worker -d
railway up storefront-frontend --path-as-root -s storefront -d   # NEXT_PUBLIC_* are build-time
railway up admin-frontend --path-as-root -s admin -d
railway up deploy/railway/caddy --path-as-root -s caddy -d
railway up deploy/railway/caddy --path-as-root -s console -d
```

- Deploy **api first**; scheduler/ai-worker after it is healthy.
- `railway redeploy` reuses the previous deployment's settings snapshot; use
  `railway up` after changing pre-deploy/start commands.
- Rollback: Railway dashboard → service → Deployments → *Redeploy* an older
  one. Migrations are additive; `app.commands.migrate` skips when the DB is
  newer, so older API code starts. Never downgrade the schema by hand.
- `.railwayignore` in each folder keeps `backend/var/` (secrets, backups),
  `.env*`, `node_modules`, `.next` out of uploads.

## 3. One-off commands

`railway ssh` needs an SSH public key on the Railway account (not registered
yet: `railway ssh keys add --key ~/.ssh/id_ed25519.pub`). Then:

```sh
railway ssh -s api -- alembic current
railway ssh -s api -- python -m app.commands.platform_admin grant you@example.com
railway ssh -s api -- python -m app.commands.smtp_check --to you@example.com
```

Without SSH, a one-off command can run as the api pre-deploy step
(`sh -c 'python -m app.commands.migrate && <command>'`) followed by
`railway up`, then the pre-deploy is set back. The first-run bootstrap was run
that way on 2026-11-12.

## 4. Secrets

- Generated once into `backend/var/railway-production-secrets.env`
  (git-ignored, mode 600): `JWT_SECRET`, `JWT_REFRESH_SECRET`,
  **`SECRETS_ENCRYPTION_KEY`**, MinIO root user/password, store-admin password.
  **Copy them into a password manager and keep `SECRETS_ENCRYPTION_KEY` apart
  from database backups**, then delete the file. Railway holds the live copies.
- Never regenerate `SECRETS_ENCRYPTION_KEY` for an existing database: brands'
  Razorpay keys become unreadable. Key rotation is not implemented.
- Store admin (per-store login, "Admin" tab / `POST /api/v1/admin/auth/login`
  on the store host): `admin@caddy-production-e45f33ac.up.railway.app`.
  `SEED_ADMIN_PHONE` is a placeholder (`+919000000001`): change it before
  MSG91 OTP is enabled.

## 5. Backups and restore

Railway volume backups need a **Pro** workspace ("Manual backups and backup
schedules are only available for Pro workspaces"). On Hobby, the `backup`
cron service does it:

1. `pg_dump -Fc`, archive TOC check, upload to the Railway bucket
   **cliq-backups** (region sin, separate from the DB and MinIO volumes) as
   `db/cliq-<UTC>.dump` with its SHA-256; retention 14 days (keeps ≥ 3).
2. Copies new product images MinIO → `media/<key>` (keys are immutable;
   `pending/` skipped).
3. **Restore drill every run**: downloads the uploaded dump, checks the
   checksum, restores into `cliq_restore_drill_<ts>` on the same server,
   compares row counts and alembic revision with the live DB, drops it.

First run 2026-11-12 09:09 UTC: dump 302 KB, 2 images copied, restore drill
`ok` (revision `f4a6b8c0d2e3`). Run it now: `railway cron run -s backup --yes`;
history: `railway cron list -s backup`.

Limits: the bucket is on Railway too (another storage system, same
provider/account); Railway buckets have no versioning and no backups of
their own. For a provider-independent copy add an external S3/R2 bucket
(`BACKUP_S3_*` variables accept any S3 endpoint) or upgrade to Pro and enable
volume backup schedules as well.

Real restore into production (stop api, scheduler, ai-worker first):

```sh
# from a shell with the Postgres 18 client and the bucket credentials
aws s3 cp --endpoint-url https://t3.storageapi.dev s3://<bucket>/db/cliq-<ts>.dump .
pg_restore --clean --if-exists --no-owner -d "$DATABASE_PUBLIC_URL" cliq-<ts>.dump
```

## 6. Domains (when a domain is bought)

Hobby allows **2 custom domains per service** (Pro: 20, more on request).
Plan: on the **caddy** service add `<root>` and `*.<root>` (the wildcard needs
the `_acme-challenge` CNAME and the TXT record Railway shows; with Cloudflare,
do not proxy those records). On **console** add `app.<root>`. Then set
`PLATFORM_ROOT_DOMAIN`, `CORS_ORIGINS`, `PUBLIC_API_URL`, `S3_*` URLs,
`NEXT_PUBLIC_*` (rebuild storefront/admin) and `APP_HOST`.

Merchant-owned custom domains are **not automatic on Railway**: each one must
be added to the caddy service through Railway's API/CLI
(`railway domain shop.brand.com -s caddy`, then the merchant creates the
CNAME + TXT Railway returns). The app's own TXT check still decides whether a
domain serves a brand. That counts against the per-service domain limit, so
on Hobby there is room for none; automating `customDomainCreate` from the
operator console is not implemented.

## 7. Monitoring

- Railway: per-service logs (`railway logs -s <svc>`), CPU/memory
  (`railway metrics -s <svc>`), deployment health checks (deploy-time only).
- In-app: operator console → System (DB, Redis, jobs, missing provider keys).
- **Not configured yet:** external uptime monitor on
  `https://caddy-production-e45f33ac.up.railway.app/health/ready`, Sentry DSN,
  `ALERT_WEBHOOK_URL` (backup failures and job failures post there once set).
