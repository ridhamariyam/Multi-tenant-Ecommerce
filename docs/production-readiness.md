# CliQ. production deployment readiness — 2026-11-12

Audit of the release after the local production rehearsal (`ffe5583`). It does
not add features. It covers what has been verified and what must be done or
checked before real customers use the platform.

**Verdict:** the stack can be deployed to a public server. The four confirmed
blockers this audit found are fixed and verified (§2). **Do not accept real
customers until the acceptance tests in §8 pass on the public server**, and in
particular until live Razorpay payments, webhooks and SMTP have each been tested.
None of the external providers has been tested live yet.

## 1. How each statement was checked

| Label | Meaning |
|---|---|
| **VERIFIED (local prod stack)** | Exercised on `docker-compose.prod.yml` running locally (Caddy local CA, `*.localhost`) |
| **IMPLEMENTED, NOT LIVE-PROVIDER VERIFIED** | Code + automated tests (provider mocked); never called against the real provider |
| **NOT IMPLEMENTED** | Does not exist |
| **REQUIRES PUBLIC SERVER** | Can only be proven with real DNS, Let's Encrypt and internet reachability |

## 2. Findings

### Fixed in this audit (verified on the local production stack)

| # | Severity | Finding | Fix and evidence |
|---|---|---|---|
| F1 | **Critical** | Per-IP rate limits were shared by **every shopper of a brand**. The storefront's server-side calls (guest checkout preview/place/payment confirm, order tracking, collection + search pages, OTP sign-in, token refresh) reached the API from the storefront container's IP. Limits: guest checkout 10/min, tracking 20/min, search 120/min, sign-in 30/min, refresh 30/5 min. So the 11th guest order in a minute would fail for everyone, and busy pages would sign customers out | `storefront-frontend/src/lib/api/client.ts` forwards the shopper's IP on uncached server-side calls (cached catalogue reads stay shared), and the middleware forwards it on refresh. The IP comes from Caddy's `X-Forwarded-For`, which Caddy sets and does not accept from clients. **Evidence:** Redis rate-limit keys showed the shopper's real address (172.24.0.1) for SSR search, browser `/api/v1` calls and console login; a spoofed `X-Forwarded-For: 1.2.3.4` was ignored; E2E 4/4 |
| F2 | **Critical** | **Rollback after a release with a migration could not start.** `alembic upgrade head` on a database migrated by a newer release fails (`Can't locate revision`), and `api` waits for `migrate`, so the documented rollback left the new version running | `migrate` now runs `python -m app.commands.migrate`: it skips (exit 0, JSON log) when the database is newer than the code, and upgrades otherwise. **Evidence:** on the stack, a "future" revision gives a skip with the API healthy; a real migration error still exits 1 and the API is not replaced. 4 new tests |
| F3 | **High** | **Container logs had no size limit** (Docker `json-file` without `max-size`). The API logs one line per request: about 2–3 GB/day at the load-test rate. That fills a typical disk within weeks | `x-logging` anchor on all 11 services: 5 × 20 MB each. Verified with `docker inspect` on every container |
| F4 | **High** | **The documented real-restore command did not work.** `-U "$POSTGRES_USER"` was expanded by the host shell (unset there), and the AI worker was left connected | `docs/deployment.md` corrected. **Evidence:** fresh dump → documented restore → 2 brands / 8 products / 3 orders, the same as the restore drill on that dump; stack healthy afterwards |

### Open: operator action before real customers

| # | Severity | Finding | Action |
|---|---|---|---|
| F5 | **High** | Backups (DB dumps and MinIO images) live on the **same server**. There is no automated off-site copy | Set up the nightly host cron/`rclone` in `deployment.md` § Backups, and copy `minio_data` (or use S3/R2 with versioning) |
| F6 | **High** | `SECRETS_ENCRYPTION_KEY` encrypts each brand's Razorpay keys. Lose it, or restore onto a server with a different key, and those keys are unreadable (brands must re-enter them) | Store it in a password manager, separate from the DB backups. Never rotate it casually: key rotation is NOT IMPLEMENTED |
| F7 | **High** | Payments, refunds, Razorpay Subscriptions, every webhook, SMTP, MSG91 OTP, Google sign-in, Shiprocket, Sheets and FASHN are **IMPLEMENTED, NOT LIVE-PROVIDER VERIFIED** | Run §8 acceptance tests with real accounts (a small real payment and refund) |
| F8 | **High** | Let's Encrypt issuance, on-demand certs for brand subdomains and custom domains, and **renewal**: REQUIRES PUBLIC SERVER (locally only Caddy's own CA was used) | §8 tests T1–T4; check renewal ~60 days in (Caddy renews automatically from `caddy_data`) |
| F9 | **High** | No external uptime check. Alerts come from inside the server, so a dead server sends nothing | Point an uptime monitor (UptimeRobot, Better Stack…) at `https://api.<root>/health/ready` and a store URL |

### Open: should fix before scaling

| # | Severity | Finding | Recommendation |
|---|---|---|---|
| F10 | Medium | Connection budget: each API worker may hold 20 DB connections; PostgreSQL allows 100 | Keep `API_WORKERS × 20 + 40 < 100` (≤ 3 workers at the default pool), or lower `DB_POOL_SIZE`/`DB_MAX_OVERFLOW`. Now in `deployment.md` |
| F11 | Medium | No CPU or memory limits on containers. A runaway build, image optimizer or AI worker can starve PostgreSQL | Add `mem_limit`/`cpus` once real usage is known; until then use an 8 GB server with 2–4 GB swap |
| F12 | Medium | Let's Encrypt: 50 new certificates per registered domain per week; each new brand subdomain uses one | Fine at launch. Beyond that, a wildcard cert via DNS-01 (Caddy DNS module), which is NOT IMPLEMENTED |
| F13 | Medium | Billing webhook order: a late, retried `subscription.charged` arriving after `subscription.cancelled` sets the brand back to ACTIVE | Ignore activation events for a cancelled subscription, or compare event timestamps |
| F14 | Medium | Mobile carrier NAT (very common in India) puts many shoppers behind one IP, which can then hit guest checkout's 10/min per IP per brand | Watch 429s in the logs after launch; raise `GUEST_CHECKOUT_RATE_LIMIT_ATTEMPTS` if real shoppers hit it |
| F15 | Medium | Single server: no high availability; the scheduler and AI worker are single instances by design (do not scale them to 2: jobs have no distributed lock) | Acceptable for launch; managed Postgres + object storage are the first steps to HA |
| F16 | Medium | No CI pipeline (tests are run by hand) | Add CI running `backend/scripts/test.sh` per folder + both frontend builds |

### Low

| # | Finding |
|---|---|
| F17 | Redis has no password. It is reachable only on the internal Docker network, which is acceptable; add `requirepass` if anything else joins that network |
| F18 | Every backend container receives the whole `.env.production` (all provider secrets) |
| F19 | `www.<root>` is not a store, so it gets no certificate. Add a Caddy redirect if you advertise `www` |
| F20 | Custom domains are set up with a CNAME, which DNS allows only on subdomains (`shop.brand.com`), not the bare apex (`brand.com`) unless the provider flattens CNAMEs |
| F21 | `NEXT_PUBLIC_*` values are baked in at build time, so changing them needs `up -d --build storefront admin` |
| F22 | The request log has no client IP (harder to investigate abuse) |

### Checked and found sound

- **Webhooks:**
  - Razorpay payment webhooks (platform + per-brand), billing webhook, FASHN token and Shiprocket token are all compared in constant time (`hmac.compare_digest`). Unsigned requests are rejected, and an unconfigured secret returns 503.
  - A paid event re-delivered is a no-op: the payment is locked `FOR UPDATE`, and PAID/REFUNDED are left alone.
  - AI credits per period are granted once (unique `(tenant_id, reference)`).
  - The platform account cannot act on brands that use their own keys.
- **Isolation:**
  - The tenant is resolved from the host, not from the client.
  - A brand webhook is scoped to that brand.
  - Guest payment verification for another brand returns 404.
  - E2E: each domain shows only its brand, and an unknown host gets no certificate.
- **Secrets:**
  - `.env*` files, the rehearsal CA and test accounts are gitignored.
  - Docker build contexts exclude `.env*`.
  - Git history has no live keys or private keys (only placeholder strings in tests and docs).
  - Production refuses to start with weak JWT secrets, `CORS_ORIGINS=*`, a missing or invalid Fernet key, or the mock AI provider.
- **Proxy:**
  - Only Caddy publishes ports.
  - Only the webhook, media and health paths of `api.<root>` are public (others 404, verified).
  - On-demand TLS is gated by `/internal/tls-allowed`.
  - Caddy ignores client-supplied `X-Forwarded-For` (verified, F1).
- **Workers:**
  - The scheduler runs each job with a timeout; a failure is logged, alerted and retried next interval; health is checked by `--check`.
  - Celery uses `acks_late` + `reject_on_worker_lost`, a fresh event loop per task, and disposes the engine afterwards.
  - The DB pool has `pre_ping` and `recycle`.

## 3. Server requirements

| | Minimum | Recommended |
|---|---|---|
| CPU | 2 vCPU | 4 vCPU (then `API_WORKERS=3`, see F10) |
| RAM | 4 GB + 2 GB swap | 8 GB + 2 GB swap |
| Disk | 40 GB SSD | 80 GB SSD (images, dumps, Docker build cache) |
| OS | Ubuntu 22.04/24.04 LTS (any Linux with Docker) | |
| Software | Docker Engine 24+, Compose v2 plugin, git, NTP time sync (signatures/JWT) | |
| Network | Public IPv4 (IPv6 optional); inbound 22, 80, 443/tcp, 443/udp only | |

Measured: on a laptop with 2 API workers, about 120 req/s with no errors, limited by API CPU.
Capacity on your server has not been measured. Run `loadtest/storefront_load.py` against it
before launch. All simulated shoppers come from one IP, so expect 429s on per-IP limits.

## 4. DNS records

Replace `cliq.example` with your root domain and `203.0.113.10` with the server IP.

| Name | Type | Value | Why |
|---|---|---|---|
| `cliq.example` | A | 203.0.113.10 | Redirects to the console |
| `*.cliq.example` | A | 203.0.113.10 | `app.`, `api.`, `media.` and every `<brand>.cliq.example` |
| same two names | AAAA | server IPv6 | Only if the server has IPv6 that reaches Docker; otherwise add none |
| `cliq.example` | CAA | `0 issue "letsencrypt.org"` | Optional hardening |
| email domain | TXT (SPF), DKIM, DMARC | from your SMTP provider | Order emails reach inboxes |
| brand custom domain | CNAME → `<brand>.cliq.example` and TXT `_cliq-verify.<domain>` | shown in the console | Per brand, when they add one |

Check before deploying: `dig +short app.cliq.example` and `dig +short anything.cliq.example` both return the server IP.

## 5. Environment variables (`.env.production`, names only)

Generate secrets with `openssl rand -hex 32`. Generate the Fernet key with
`python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.

- **Required to start:**
  - `ENVIRONMENT` (=production), `CLIQ_VERSION`
  - `PLATFORM_ROOT_DOMAIN`, `STOREFRONT_URL_TEMPLATE`, `ACME_EMAIL`, `CADDY_EXTRA_GLOBAL_OPTIONS` (empty)
  - `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
  - `JWT_SECRET`, `JWT_REFRESH_SECRET`, `SECRETS_ENCRYPTION_KEY`, `CORS_ORIGINS`
  - `STORAGE_BACKEND`, `S3_BUCKET`, `S3_REGION`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_ENDPOINT_URL`, `S3_PUBLIC_BASE_URL`
  - `SEED_TENANT_NAME`, `SEED_TENANT_SLUG`, `SEED_TENANT_DOMAIN`, `SEED_ADMIN_EMAIL`, `SEED_ADMIN_PHONE`, `SEED_ADMIN_PASSWORD` (≥ 12 chars)
- **Tuning:** `API_WORKERS`, `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `BACKUP_INTERVAL_SECONDS`, `BACKUP_KEEP_DAYS`, `LOG_LEVEL`, `DISK_ALERT_FREE_PERCENT`
- **Monitoring:** `SENTRY_DSN`, `SENTRY_TRACES_SAMPLE_RATE`, `ALERT_WEBHOOK_URL`
- **Email:** `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `EMAIL_FROM_ADDRESS`, `EMAIL_FROM_NAME`
- **Razorpay (platform account: your store and plan billing):** `RAZORPAY_ENVIRONMENT`, `PRODUCTION_RAZORPAY_API_KEY`, `PRODUCTION_RAZORPAY_API_SECRET`, `RAZORPAY_WEBHOOK_SECRET`, `RAZORPAY_BILLING_WEBHOOK_SECRET`, `RAZORPAY_PLATFORM_TENANT_SLUGS`, `NEXT_PUBLIC_RAZORPAY_KEY_ID` (build time)
- **Sign-in:** `MSG91_AUTH_KEY`, `NEXT_PUBLIC_MSG91_WIDGET_ID`, `NEXT_PUBLIC_MSG91_TOKEN_AUTH`, `GOOGLE_CLIENT_ID`, `NEXT_PUBLIC_GOOGLE_CLIENT_ID`
- **Shipping / Sheets / AI:** `SHIPROCKET_EMAIL`, `SHIPROCKET_PASSWORD`, `SHIPROCKET_TENANT_ID`, `SHIPROCKET_WEBHOOK_TOKEN`, `GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON`, `AI_PROVIDER`, `FASHN_API_KEY`, `FASHN_WEBHOOK_SECRET`

`chmod 600 .env.production`. It is gitignored; never paste its values into chat, tickets or commits.

## 6. Prioritized deployment checklist

1. [ ] Server provisioned to §3; firewall allows only 22/80/443; SSH by key only; swap enabled.
2. [ ] DNS records from §4 resolve to the server.
3. [ ] `.env.production` filled (§5). Fernet key and DB password stored in a password manager.
4. [ ] First deploy (§7.1); `ps` shows every service healthy, `migrate` exited 0.
5. [ ] Bootstrap run; platform admin granted.
6. [ ] Acceptance tests T1–T6 pass (TLS, isolation, routing).
7. [ ] Off-site backup cron installed and one copy confirmed elsewhere (F5); restore drill passes on it.
8. [ ] Uptime monitor (F9), `ALERT_WEBHOOK_URL` and `SENTRY_DSN` set; a test alert received (T12).
9. [ ] SMTP configured; T9 passes (an order email arrives, not in spam).
10. [ ] Razorpay live keys + both webhooks; T7–T8 pass (real ₹1–10 payment, refund, webhook delivered).
11. [ ] Razorpay Subscriptions enabled; T10 passes (a brand subscribes; cancel later).
12. [ ] Optional providers as needed (MSG91, Google, Shiprocket, Sheets, FASHN), each tested once live.
13. [ ] System tab in the platform console shows every job ok and every configured provider ✓.
14. [ ] Only then: announce, onboard the first real brand.

## 7. Commands

All commands run in the repository directory on the server. Set this once per shell:

```sh
C="docker compose -f docker-compose.prod.yml --env-file .env.production"
```

### 7.1 First deploy

```sh
git clone <repo> cliq && cd cliq
cp .env.production.example .env.production && chmod 600 .env.production   # then fill it in
$C up -d --build --wait
$C ps                                                    # all healthy; migrate "Exited (0)"
$C run --rm api python -m app.commands.bootstrap         # operator store + admin (idempotent)
# register your merchant account at https://app.<root>/admin/register, then:
$C run --rm api python -m app.commands.platform_admin grant you@example.com
```

### 7.2 Update

```sh
$C exec backup sh /usr/local/bin/backup.sh               # backup first
git pull
sed -i 's/^CLIQ_VERSION=.*/CLIQ_VERSION=<new number>/' .env.production
$C up -d --build --wait
$C logs --tail=50 migrate api
```

### 7.3 Rollback

```sh
sed -i 's/^CLIQ_VERSION=.*/CLIQ_VERSION=<previous number>/' .env.production
git checkout <previous tag or commit>     # keep compose/Caddy config in step with the images
$C up -d --wait                          # no --build: the previous images are still on disk
$C logs migrate                          # after a migration release: "status": "skipped"
```

Migrations are additive, so the previous code runs on the newer schema; `migrate`
skips instead of failing (F2). This needs the release you roll back **to** to include
`app/commands/migrate.py` (this audit's commit or later). Rolling back further than
that after a migration needs `$C up -d --no-deps api scheduler ai-worker storefront admin`.
**Never run `alembic downgrade` in production.**
If the previous code cannot work with the new schema, restore the backup taken
in 7.2 (`deployment.md` § Real restore). That loses orders placed since the
backup, so prefer fixing forward. Old images are removed only by `docker image
prune`, so keep at least the last two versions.

### 7.4 Backups

```sh
$C exec backup sh /usr/local/bin/backup.sh                                  # on demand
docker run --rm -v cliq_backups:/b -v "$PWD":/out alpine \
    sh -c 'cp "$(ls -t /b/cliq-*.dump | head -1)" /out/latest.dump'
deploy/backup/restore-drill.sh latest.dump                                   # monthly
```

## 8. Post-deployment acceptance tests

Run all of them on the public server, and record date, result and evidence for each.
Set `R=<root domain>`.

| # | Test | Pass when |
|---|---|---|
| T1 | `curl -sI https://app.$R/admin/signin` and `https://api.$R/health/ready` | 200, certificate issuer is Let's Encrypt (`openssl s_client -connect app.$R:443 </dev/null \| grep issuer`) |
| T2 | Open `https://<seed slug>.$R` and a newly published brand's subdomain | Store renders over HTTPS with a valid certificate on first visit |
| T3 | `curl -sv https://not-a-brand.$R` | TLS handshake fails (no certificate is issued) |
| T4 | Add a custom domain to a test brand, set its CNAME + TXT, verify in the console | Domain serves that brand with a valid certificate |
| T5 | `curl -s -o /dev/null -w '%{http_code}' https://api.$R/api/v1/admin/orders` | 404 (private API not exposed) |
| T6 | E2E suite from your laptop: `cd e2e && E2E_STORE_URL=https://<slug>.$R E2E_SECOND_STORE_URL=https://<brand2>.$R E2E_SECOND_BRAND_NAME=… E2E_CONSOLE_URL=https://app.$R/admin E2E_MERCHANT_EMAIL=… E2E_MERCHANT_PASSWORD=… npx playwright test` | 4/4 |
| T7 | Guest buys a ₹1–10 product online with a real card/UPI on a brand with its own live Razorpay keys | Order PAID in the console; Razorpay dashboard shows the webhook delivered with 200 |
| T8 | Refund that order from the console | Razorpay shows the refund; order/payment shows REFUNDED after `refund.processed` |
| T9 | Place an order with an email address | Confirmation email arrives (check headers: SPF/DKIM pass) |
| T10 | A test brand subscribes to Starter; then cancel | Plan becomes Starter, `subscription.*` webhooks are 200; after cancel the brand falls back to Free limits |
| T11 | Submit 11 guest checkouts in a minute from two different networks | Only the network that exceeded the limit gets 429 (proves F1 on the public server) |
| T12 | Temporarily set `DISK_ALERT_FREE_PERCENT=99`, restart `scheduler` | Alert message arrives at `ALERT_WEBHOOK_URL`; set it back |
| T13 | Backup → copy off-site → restore drill on the copy | `restore drill passed` |
| T14 | Rollback drill once before launch: deploy N+1, roll back to N (§7.3) | API healthy on N; store works |
| T15 | After ~60 days | Certificates renewed (expiry date moved forward) without intervention |

## 9. Status summary

| Area | Status |
|---|---|
| Stack, health checks, migrate-before-API, rollback, logs capped | VERIFIED (local prod stack) |
| Backup, restore drill, real restore | VERIFIED (local prod stack); off-site copy: operator task |
| Caddy routing, on-demand TLS gating, private API | VERIFIED (local prod stack, local CA); Let's Encrypt and renewal: REQUIRES PUBLIC SERVER |
| Multi-tenant isolation, per-shopper rate limits | VERIFIED (local prod stack + tests) |
| Scheduler jobs, AI worker process | VERIFIED (local prod stack); FASHN generation: NOT LIVE-PROVIDER VERIFIED |
| Razorpay payments/refunds/webhooks, brand-own keys (encrypted) | IMPLEMENTED, NOT LIVE-PROVIDER VERIFIED (only test mode in dev) |
| Razorpay Subscriptions billing | IMPLEMENTED, NOT LIVE-PROVIDER VERIFIED |
| SMTP email, MSG91, Google sign-in, Shiprocket, Sheets, Sentry, alert webhook | IMPLEMENTED, NOT LIVE-PROVIDER VERIFIED |
| Wildcard certificate (DNS-01), CI, metrics, encryption-key rotation, HA | NOT IMPLEMENTED |
