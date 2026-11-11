# Deploying CliQ.

One server runs the whole platform with Docker Compose. Everything below has
been exercised on a laptop with `PLATFORM_ROOT_DOMAIN=localhost` (see
"Rehearse locally"); it has **not** yet been run on a public server with real
DNS and Let's Encrypt certificates.

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
- Ports 80 and 443 open (80 is needed for Let's Encrypt).

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

- Razorpay webhook: `https://api.<root>/api/v1/payments/razorpay/webhook`, secret = `RAZORPAY_WEBHOOK_SECRET`
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
  newer (additive) schema, so roll back code as above. If it does not, restore the
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
  docker compose -f docker-compose.prod.yml --env-file .env.production stop api scheduler storefront admin
  docker compose -f docker-compose.prod.yml --env-file .env.production exec -T postgres \
      pg_restore --clean --if-exists --no-owner -U "$POSTGRES_USER" -d "$POSTGRES_DB" < latest.dump
  docker compose -f docker-compose.prod.yml --env-file .env.production up -d
  ```

## Monitoring

What exists today:

- Health checks on every service (`docker compose ps`); `restart: unless-stopped`
  brings crashed services back.
- `GET https://api.<root>/health/ready` (checks the database and Redis) — point an
  uptime monitor (UptimeRobot, Better Stack, …) at it and at a storefront URL.
- Structured logs: Caddy access logs and the scheduler/backup lines are JSON
  (`docker compose logs -f scheduler | grep '"status": "failed"'`).

Not yet built (see `docs/technical-audit.md`): error reporting (Sentry), metrics,
disk-usage alerts. Until then, at least alert on disk space from the host
(e.g. a cron `df` check) since Postgres, MinIO and backups share the disk.

## Rehearse locally

The same stack runs on a laptop with Caddy's own certificate authority:

```sh
cp .env.production.example .env.prodtest
# PLATFORM_ROOT_DOMAIN=localhost, CADDY_EXTRA_GLOBAL_OPTIONS=local_certs,
# STOREFRONT_URL_TEMPLATE=https://{subdomain}.{root}, random secrets
CLIQ_ENV_FILE=.env.prodtest docker compose -p cliq-prodtest -f docker-compose.prod.yml \
    --env-file .env.prodtest up -d --build
curl -k https://app.localhost/admin/signin
```

Browsers resolve `*.localhost` to your machine; accept the local certificate (or
trust Caddy's root CA from the `caddy_data` volume).

## Environments

- **Production:** `.env.production` (`ENVIRONMENT=production`; the API refuses to
  start with weak JWT secrets, `CORS_ORIGINS=*` or the mock AI provider).
- **Staging:** a second server (or compose project) with its own
  `.env.staging`, its own domain (e.g. `staging-cliq.example.com`), Razorpay test
  keys and `ENVIRONMENT=staging`. Never point staging at production's database.
- **Development:** `docker-compose.yml` + `npm run dev` in each frontend (README).
