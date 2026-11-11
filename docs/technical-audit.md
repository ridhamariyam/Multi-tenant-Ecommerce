# CliQ. technical audit — 2026-11-11

An audit of the repository as it stands, written before the next round of
work. Every claim below was checked against the code, the running dev stack
or the test suite on this date. "Works" means the whole path (UI → API →
database) was exercised, not that a model or route exists.

Status vocabulary used throughout:

| Status | Meaning |
|---|---|
| **COMPLETE AND TESTED** | Whole workflow exercised end to end, automated tests exist |
| **IMPLEMENTED, NOT LIVE-VERIFIED** | Code and tests exist; depends on a provider or credentials never used live |
| **PARTIAL** | Some layers exist (e.g. API without UI, models without API) |
| **NOT IMPLEMENTED** | Nothing usable exists |
| **BLOCKED (EXTERNAL)** | Needs credentials, accounts or infrastructure outside the repo |

---

## 1. What exists

### Repository layout

| Part | Tech | Notes |
|---|---|---|
| `backend/` | FastAPI, async SQLAlchemy, Alembic, Postgres 16, Redis, MinIO/S3 | **290 API operations** (148 under `/admin`, 39 catalogue, 23 storefront, 17 platform). Single Dockerfile. |
| `storefront-frontend/` | Next.js 15.5 (App Router, Turbopack) | Shopper site. **No automated tests.** |
| `admin-frontend/` | Next.js 16 shell hosting a React Router SPA (Vite for tests), React 19 | Per-store admin. 38 test files (Vitest). |
| `docker-compose.yml` | postgres, redis, minio, api, order-expiry, shipment-sync, order-sheets | Dev-oriented. No frontend images, no reverse proxy, no Celery worker. |
| `docs/` | platform-architecture.md (phases 1–6), shiprocket.md | Architecture doc's phase table is out of date (see §2). |

### Backend test suite

~1,330 test functions in `backend/tests` (orders 336, catalogue 246, payments 100,
pricing 76, admin 64, search 59, brands 49, auth 48, shipments 47, coupons 44,
ratings 42, cart 42, core 31, gst_defaults 28, wishlist 20, tenants 18, dashboard 17,
account 15), plus parametrised cases. Last full run (per folder, 2026-11-07):
1,550 passing. Folders run today: orders + core = 430 passed; cart, payments, coupons,
pricing = 290 passed. The suite runs in throwaway containers (`scripts/test.sh`).
On this 7.4 GB machine the whole suite in one process is killed for memory; run per
folder.

---

## 2. Module status

### Shopper storefront

| Module | Status | Evidence / gap |
|---|---|---|
| Runway home (looks, pins, add-look) | COMPLETE AND TESTED (manually) | Browser-verified; no automated test |
| Catalogue, collections, filters, sort | COMPLETE AND TESTED (manually) | API tested; UI verified at 1280/390 px |
| Product page, variants, size chart, reviews | COMPLETE AND TESTED (manually) | |
| Search + suggestions + NL query understanding | IMPLEMENTED | Backend tests (59); UI checked |
| Wishlist | COMPLETE AND TESTED (manually) | |
| Guest cart + signed-in cart, merge on sign-in | COMPLETE AND TESTED | Fixed "page reloads on add" bug |
| Guest checkout (COD) + public tracking | COMPLETE AND TESTED | Order ORD-100007 placed in browser |
| Signed-in checkout, Razorpay, invoices, order history | IMPLEMENTED, NOT LIVE-VERIFIED | Backend tests pass; the browser journey has not been run signed in (customer login needs OTP via MSG91) |
| Customer OTP / Google sign-in | BLOCKED (EXTERNAL) | Needs MSG91 widget keys / Google client id |
| SEO (meta, OG, JSON-LD, sitemap, robots) | COMPLETE (2026-11-11) | Per-request site URL |
| Multi-brand: storefront serves the brand of the visited domain | COMPLETE AND TESTED (2026-11-11) | §7 |
| Per-brand theme (logo, colours, favicon, name) | PARTIAL | Name, logo, colours, favicon, SEO, share image and manifest follow the brand. Page copy (About, FAQ, policies, contact, some error texts) and the runway looks are still CliQ's |
| Unknown / unpublished / suspended store pages | COMPLETE AND TESTED | "This store isn't available" page, noindex |
| CMS pages, blog, policies | PARTIAL | Backend CMS exists; policies page is static TSX; no blog UI |

### Store admin (per brand)

| Module | Status |
|---|---|
| Dashboard, reports, GST reports, top products | IMPLEMENTED (API tests + Vitest) |
| Products, variants, categories, images, bulk import | IMPLEMENTED |
| Inventory + movement history, low stock | IMPLEMENTED |
| Orders, status machine, notes, tracking events, invoices | IMPLEMENTED |
| Refunds (Razorpay) | IMPLEMENTED, NOT LIVE-VERIFIED |
| COD settings, blacklist, advance | IMPLEMENTED |
| Shiprocket booking / AWB / labels / tracking / webhooks | IMPLEMENTED, NOT LIVE-VERIFIED (`docs/shiprocket.md`) |
| Coupons | IMPLEMENTED |
| Reviews moderation + review requests | PARTIAL — review-request emails are logged, not sent (no email provider) |
| Staff + fine-grained permissions + audit log | IMPLEMENTED |
| Google Sheets order export | IMPLEMENTED, NOT LIVE-VERIFIED (needs service account key) |
| Customer tags, segments, consent, export/delete workflow | PARTIAL — notes and blocking exist; no segments/consent records |
| Abandoned cart recovery, campaigns, email/SMS/WhatsApp | NOT IMPLEMENTED |

### Multi-brand SaaS

| Module | Status |
|---|---|
| Merchant accounts, login, refresh rotation | COMPLETE AND TESTED (API + admin UI) |
| Brand registration, switching, members, roles | COMPLETE AND TESTED (API + admin UI) |
| Store settings, publish, custom domains (TXT generated, admin-verified) | COMPLETE AND TESTED (API + admin UI); TXT not checked automatically, logo/favicon are URLs (no upload yet) |
| Platform admin (overview, brands, suspend/reinstate, domains with DNS check) | COMPLETE AND TESTED (API + UI), actions audited in the brand's log |
| Password recovery, email verification for merchants | Password reset: IMPLEMENTED, NOT LIVE-VERIFIED (needs SMTP). Email verification: NOT IMPLEMENTED |
| Onboarding checklist, demo data | NOT IMPLEMENTED |
| Subscription plans / brand subscriptions | IMPLEMENTED, NOT LIVE-VERIFIED — limits enforced and tested; Razorpay Subscriptions never called live (Step 8) |
| Credits / usage ledger | COMPLETE AND TESTED (API + console) |
| Virtual model library | PARTIAL — admin/brand API exists, no UI |
| AI try-on (FASHN) via Celery | IMPLEMENTED (worker in compose, API, UI); BLOCKED (EXTERNAL) for live generation (FASHN key) |
| Lookbooks | COMPLETE AND TESTED (API + console + storefront runway) |

### Infrastructure

| Item | Status |
|---|---|
| Backend image + healthchecks | IMPLEMENTED |
| Storefront / admin Docker images | COMPLETE AND TESTED (built and run in the production rehearsal) |
| Reverse proxy, TLS, wildcard subdomains, custom-domain certs | Verified on the local production stack (Caddy local CA, on-demand certs gated by the API). Let's Encrypt issuance/renewal and real DNS: REQUIRES PUBLIC SERVER |
| Scheduled jobs | COMPLETE AND TESTED: one scheduler process (7 jobs, timeouts, JSON logs, healthcheck, job status in the System tab); AI Celery worker in compose |
| CI pipeline | NOT IMPLEMENTED |
| Error monitoring (Sentry or similar), metrics | Sentry + alert webhook: IMPLEMENTED, NOT LIVE-VERIFIED (no DSN/webhook). Metrics: NOT IMPLEMENTED |
| Structured logging | COMPLETE AND TESTED (JSON lines, request ids; container logs capped 5 × 20 MB) |
| Backups | COMPLETE AND TESTED locally: nightly dump service + restore drill (passes on a real dump, fails on a corrupt one); off-site copy is an operator task |
| Staging / production configs | IMPLEMENTED (`.env.production.example`, production refuses weak settings); staging server not set up |
| End-to-end tests (Playwright) | NOT IMPLEMENTED |
| Load tests | NOT IMPLEMENTED — no capacity figures exist |

---

## 3. Broken or risky

### 3.1 Storefront always serves one brand (critical for multi-brand)

The backend resolves the brand from the request's `Host`. The storefront's
server-side API calls go to `NEXT_PUBLIC_API_URL` without saying which domain the
shopper visited, so the backend sees the API's own host. In development that host
is `localhost`, which falls back to the seed brand; in production it would be an
unknown host and every page would fail. Four client components
(`HeaderSearch`, `QuickAddSheet`, wishlist `AddToBagModal`/`WishlistCard`) call
the API host straight from the browser, with the same problem.

Fix (in progress, §5 step 1): forward the visited host on server calls
(`X-Forwarded-Host`, honoured when `TRUST_FORWARDED_HOST=true`), send browser calls
through a same-origin `/api/v1` proxy, and drive name/logo/theme/SEO from
`GET /storefront/resolve`. Next's fetch cache keys include request headers, so
per-host caching stays separated.

### 3.2 Other findings

| # | Finding | Severity |
|---|---|---|
| R1 | Dev database was two migrations behind the code (fixed). Production now runs `migrate` to completion before the API starts. | Resolved in prod compose |
| R2 | Storefront dependencies: 7 known vulnerabilities (`npm audit --omit=dev`): critical `swiper`, high `katex`/`postcss`, moderate `uuid`, `quill`. Admin: 0. | High |
| R3 | `NEXT_PUBLIC_SITE_URL` set in `.env` forces one site URL for every brand (canonical, sitemap). | Medium |
| R4 | ~~Scheduled jobs are `while sleep` loops~~ Production uses `app.commands.scheduler` (contained failures, timeouts, JSON logs, healthcheck). No alerting yet. | Low |
| R5 | Review-request and order emails are logged instead of sent. | Medium (product) |
| R6 | ~~Custom domains are verified by hand~~ TXT ownership is now checked by DNS (merchant *Check now*, operator *Check DNS*); certificate issuance for custom domains is still a deployment task. | Medium |
| R7 | Uploaded images from before the S3 switch still live on a Docker volume. | Low |
| R8 | A container `tws-ecommerce-core-jobs-1` from an unrelated checkout (`~/TWS/...`) runs on the same machine and network. Not part of this repo; left untouched. | Info |
| R9 | Row-level security is not enabled; isolation relies on application queries + composite FKs (tested). | Accepted risk, documented |

### Security posture (what is already good)

- Tenant isolation is enforced server-side: customer tokens carry `tenant_id` and are
  rejected on another brand's host; brand tokens are re-checked against membership
  every request; brand ids from clients are never trusted. Cross-tenant attack tests
  exist (`tests/brands/test_tenant_isolation.py`, `test_storefront_resolve.py`).
- Rotating refresh tokens with reuse detection, httpOnly cookies, rate limits on
  login/OTP, idle timeout, security headers, request ids, typed error envelope that
  never echoes submitted values.
- Razorpay: signature verification, server-side amount/currency/capture checks,
  webhook signature + idempotent event handling.
- Money in `Decimal` with ROUND_HALF_UP; a DB check constraint enforces the order total
  equation.

---

## 4. Database and migrations

- Alembic, linear history, head `a7c4e91b2d55` (order sheet export).
- Composite `(tenant_id, id)` foreign keys on tenant-owned tables.
- Applied to dev today: `a7c2e5f81b30` (media assets, virtual models),
  `c3d9f4a6e1b2` (AI jobs, credits, plans, lookbooks), `a7c4e91b2d55`.
  Backup: `backend/var/backups/db-before-order-sheets-*.dump`.
- Needed: a deploy step that runs `alembic upgrade head` before the new API starts, and a
  documented downgrade/restore path.

## 5. Roadmap (order of execution)

Ordered by what blocks real merchants first. Each step ends with tests, type
checks, builds and an update to this table.

| # | Step | Status |
|---|---|---|
| 1 | Storefront tenant resolution: host forwarding, same-origin API proxy, brand from `/storefront/resolve` (name, logo, colours, favicon, SEO), unknown/unpublished store pages | **Done** (2026-11-11) — see §7 |
| 2 | Storefront dependency vulnerabilities (R2) | **Done** (2026-11-11) — see §7 |
| 3 | Merchant console UI: sign up / sign in, brand list + switch, create brand, store settings, publish, domains, members — on the existing platform API | **Done** (2026-11-11) — see §7 |
| 4 | Platform admin UI: brands, suspend/activate, verify domains | **Done** (2026-11-11) — see §7 |
| 5 | Production deployment: storefront + admin Dockerfiles, reverse proxy with wildcard TLS, migrate-on-deploy, backup schedule + restore drill, env templates for staging/prod | **Done and rehearsed locally** (2026-11-12); not yet on a public server — see §7 |
| 6 | Observability: structured JSON logs, error reporting hook (Sentry DSN optional), job health | **Done** (2026-11-11) — see §7 |
| 7 | E2E (Playwright): guest purchase, admin order handling, two-brand isolation | **Done** (2026-11-11) — `e2e/`, runs on installed Chrome; see §7 |
| 8 | Subscriptions API + plan limits enforced server-side; billing provider integration | **Done** (2026-11-11) — Razorpay Subscriptions; live charge not verified; see §7 |
| 9 | Merchant password reset + email provider adapter (transactional email) | **Done** (2026-11-11), SMTP delivery not live-verified (no SMTP account yet) — see §7 |
| 10 | Customer segments/consent, abandoned carts, campaigns | **Done** (2026-11-11) — see §7 |
| 11 | AI track: Celery worker service, try-on API + UI, credits API, lookbooks | **Done** (2026-11-11) — FASHN generation BLOCKED on API key; see §7 |
| 12 | Load test (k6 or Locust) against a production-like stack | **Done** (2026-11-12) on the local production stack — see §7 |

## 6. External dependencies still needed

| Dependency | Needed for |
|---|---|
| MSG91 auth key + widget | Customer OTP sign-in |
| Google OAuth client id | Google sign-in |
| Razorpay live keys + webhook secret | Online payments, refunds |
| Shiprocket API user | Courier booking and tracking |
| Google service account key | Sheets order export |
| Email / SMS / WhatsApp provider | Notifications, password reset, campaigns |
| Billing provider (e.g. Razorpay Subscriptions) | SaaS subscriptions |
| FASHN API key | AI try-on |
| Domain + DNS + server(s) + TLS | Any production deployment |

**This platform is not production-ready today.** The single-brand store (CliQ.) is close:
its remaining blockers are provider credentials and deployment infrastructure. The
multi-brand SaaS is not: there is no merchant UI, storefronts do not yet follow the
visited domain, and there is no billing.

## 7. Change log

### 2026-11-11 — Step 1: storefront follows the visited domain

- `storefront-frontend/src/lib/api/visited-host.ts`: server-side API calls send
  `X-Forwarded-Host` = the shopper's host (Next's fetch cache keys on headers, so
  cached catalogue reads are per brand). Middleware token refresh and the invoice PDF
  route pass it explicitly.
- `next.config.ts` rewrites `/api/v1/*` to the API; browser calls use the storefront's
  own origin (`lib/env.ts`), and Next's proxy sets `X-Forwarded-Host` itself.
- `lib/storefront/brand.ts` reads `GET /storefront/resolve` (cached 60 s per domain).
  The root layout uses it for title template, description, Open Graph, favicon and the
  brand palette (`primary_color`/`secondary_color` override the theme's CSS
  variables); header, footer and runway header show the brand's logo or name
  (`components/BrandLogo.tsx`). The `/og` share image and the web manifest are per brand.
- Unknown, unpublished or suspended domains render `StoreUnavailable` (noindex).
- CliQ.'s own identity is data now: store `logo_url = /images/cliq-wordmark.svg`
  (drawn as the CliQ. lockup) and the tenant description; `seed_cliq_demo` sets both and
  selects the brand by `SEED_TENANT_SLUG` instead of requiring a single tenant.
- The runway's curated looks are CliQ.'s; looks with none of the visited brand's
  products are dropped, and a store with no looks opens on `/products`.
- Dev `.env`: `TRUST_FORWARDED_HOST=true` (backup in `backend/var/backups/`).
- Verified: `localhost:3000` (CliQ.) and `northwind.localhost:3000` (test brand
  "Northwind", created through the platform API) render their own name, catalogue and
  sitemap; `nope.localhost:3000` shows the unavailable page; browser quick-add works
  through the proxy. Tests: `backend/tests/brands/test_forwarded_host.py` (5) — brands
  folder 54 passed. Storefront type check and production build pass.

### 2026-11-11 — Step 2: storefront dependencies

- 40 runtime and 6 dev dependencies left over from the original template were never
  imported (swiper, katex, react-quill-new, uuid, bootstrap, jquery, fullcalendar,
  apexcharts, datatables, …). Removed. The storefront now depends on next, react,
  react-dom, react-toastify and wowjs only.
- Next 15.5 pins postcss 8.4.31 (build-time only, our own CSS); overridden to ^8.5.23
  via `overrides` in package.json.
- `npm audit`: 0 vulnerabilities (was 7: 1 critical, 1 high). Type check, production
  build and all 13 public pages pass; product page checked in the browser.

### 2026-11-11 — Step 3: merchant console (admin app)

- **Merchant mode** in `admin-frontend`: the sign-in page defaults to *Merchant*
  (email + password, `/platform/auth/*`); the old per-store Admin/Staff logins remain as
  tabs. `/register` creates a merchant account.
- `/brands`: the merchant's brands (role, live/unpublished, store address, suspended);
  *Manage* opens one; *Create brand* (name + suggested store address) creates brand +
  store and opens it with the returned token. First-run shows the create form directly.
- Opening a brand stores its short-lived brand token as the admin access token, so every
  existing admin screen works unchanged. Brand tokens have no refresh token: on a 401 the
  client asks `/brands/{id}/switch` with the platform session (rotating that session with
  `/platform/auth/refresh` if needed) and retries. Platform calls use the platform token
  (`request(..., { session: "platform" })`).
- New screens (owner/admin, merchant mode only): **Store & branding** (publish/unpublish
  with confirmation, name, address, theme, colours, logo/favicon URLs with preview,
  custom domains with CNAME/TXT instructions, remove with confirmation) and **Team**
  (add by merchant email with role, change role, remove). Sidebar shows the open brand
  and *Switch brand*.
- Tests: `src/screens/merchant.test.tsx` (6 journeys: sign-in → open brand, first brand,
  token renewal, publish + domain, team, per-store login cannot reach store settings).
  Existing suite flakiness traced to 5 s/1 s timeouts under load (failing set changed
  between runs; all pass with time); raised `testTimeout` and Testing Library
  `asyncUtilTimeout`. Admin: 214/214 tests twice in a row, lint clean, build passes.
- Verified against the live API through the admin proxy: sign-in, brand list, open,
  `/auth/me` as ADMIN, save colours, domains, team; the Northwind storefront rendered the
  new colours within a minute. (Browser extension disconnected mid-check; the UI paths
  are covered by the Vitest journeys.)
- Not yet: logo/favicon **upload** (URLs only), password reset (needs an email
  provider), email invitations for teammates without an account, onboarding checklist.

### 2026-11-11 — Step 4: platform administration

- Backend:
  - `app/stores/dns_check.py`: looks up `_cliq-verify.<domain>` TXT (DNS only — no HTTP
    to the domain, so no SSRF), 5 s timeout, failures reported, never treated as success.
  - `POST /brand/domains/{id}/check` (owner/admin): a matching record verifies the domain;
    logged in the brand's activity log.
  - Platform: `GET /platform/admin/overview` (counts only: brands by status, live
    stores, pending domains, merchant accounts — no orders/customers),
    `GET /platform/admin/domains` (pending/verified, search, brand name),
    `POST /platform/admin/domains/{id}/check`; brand list now returns suspension date
    and reason.
  - Every operator action (suspend, reinstate, verify by hand or by DNS) is written to the
    affected brand's own activity log as `CliQ. platform (<email>)`, role
    `PLATFORM_ADMIN` (`record_platform_action`).
  - Tests: `tests/brands/test_platform_admin.py` (9; DNS stubbed) — brands + admin folders
    127 passed.
- Admin app: `/platform` (operators only; linked from the brand list): totals, brands
  (search, status filter, suspend with required reason, reinstate), domains (pending by
  default, *Check DNS* with the expected/found records, *Verify manually* with
  confirmation). Merchants get *Check now* on their own domains. Tests: 3 platform + 6
  merchant journeys; admin suite 217/217; build passes.
- **Bug found and fixed in live testing:** a suspended or unpublished store stayed
  online. The storefront cached `/storefront/resolve` for 60 s, and Next keeps serving
  a cached success when the revalidation answers 404, so the stale "open" answer never
  expired. The lookup is now `no-store` (one indexed query per render, shared through
  React `cache()`). Verified live: suspending Northwind takes its storefront offline on
  the next request; reinstating brings it back; the brand's token is refused (403) while
  suspended; both actions appear in Northwind's activity log.
- Test operator for local dev: in `backend/var/dev-test-accounts.md` (gitignored),
  granted with `python -m app.commands.platform_admin grant`.

### 2026-11-11 — Step 5: production deployment (written; partly verified)

Files: `docker-compose.prod.yml`, `deploy/Caddyfile`, `deploy/backup/backup.sh`,
`deploy/backup/restore-drill.sh`, `storefront-frontend/Dockerfile`,
`admin-frontend/Dockerfile` (+ `.dockerignore`s), `.env.production.example`,
`docs/deployment.md`; backend `app/commands/scheduler.py`, `app/tenants/tls.py`.

- Only Caddy publishes ports. `app.<root>` → console, `api.<root>` → webhooks/media/health
  only, `media.<root>` → MinIO, `<root>` → redirect, every other host → storefront.
  Storefront certificates are issued on demand only for hosts the API approves
  (`/api/v1/internal/tls-allowed`: platform hosts, active brands' subdomains, verified
  custom domains).
- `migrate` (`alembic upgrade head`) must complete before `api` starts.
- Backend production image installs `requirements.txt` only (build arg); dev/test image
  unchanged. Frontends: Next `output: 'standalone'`, non-root user, healthchecks.
  Storefront image hosts come from the configured API/media URLs. Admin now sends
  security headers (HSTS, nosniff, `X-Frame-Options: DENY`, …).
- `.env.production`, `.env.staging`, `.env.prodtest` are git-ignored.

Verified:
- Caddy validates the config for a real domain and for `localhost`.
- Tests: scheduler (6) + TLS allow-list (5) + platform/resolve (14) = 25 passed.
- Scheduler ran against the dev stack: all 5 jobs `ok`, `--check` healthy.
- Backup script dumped the dev DB; restore drill restored it into a throwaway
  PostgreSQL (migration a7c4e91b2d55, 2 brands, 10 products, 7 orders, 12 customers,
  totals consistent) and exits 1 on a truncated dump.

**Not verified:** building the three production images and running the whole stack
behind Caddy. The build ran out of disk (the machine had 0 MB free; ~0.9 GB after
clearing Docker's build cache). Needs ~4 GB free, or a server. Nothing has been run on
a public server with real DNS or Let's Encrypt.

### Step 6 — Observability (2026-11-11)

- `app/core/observability.py`: JSON log formatter (request id + extra fields), uvicorn logs routed through it, one `app.request` line per request (health checks at debug); optional Sentry (`SENTRY_DSN`, scrubs cookies/auth/cart-token headers and bodies); `send_alert()` to a Slack/Discord/Google Chat webhook, throttled per problem with Redis.
- Unhandled API errors are now logged with traceback + request id (they were silently turned into 500s before) and reported to Sentry.
- Scheduler records each job's last outcome in Redis (`cliq:jobs`), alerts on failure, and has a new `disk-space` job (alerts under `DISK_ALERT_FREE_PERCENT`).
- `GET /platform/admin/system` + **System** tab in the operator console: database, Redis, jobs (ok / failed / not running / never ran), provider credentials configured or missing.
- Storefront and console: `instrumentation.ts` logs server render errors as JSON.
- Tests: `tests/core/test_observability.py` (10), system-health API test, console test. Verified live: API with `LOG_FORMAT=json` against the dev database writes JSON request lines with the caller's request id.
- Not verified: Sentry delivery (no DSN) and a real webhook (none given) — both covered by unit tests with fakes only.


### Payments — each brand's own Razorpay, guests pay online (2026-11-11)

- Decision (user): each brand connects its own Razorpay account; the platform's `.env` keys serve only `RAZORPAY_PLATFORM_TENANT_SLUGS` (default: the seeded operator store). Avoids the platform acting as a payment aggregator.
- `payment_gateway_accounts` (migration `b8e2f0c4d6a1`): key id, key secret + webhook secret encrypted with `SECRETS_ENCRYPTION_KEY` (Fernet; required in production). Keys are checked against Razorpay before saving and never returned.
- Razorpay adapter is scoped per brand (`gateway.scoped()` / ContextVar); per-brand webhook `POST /payments/razorpay/webhook/{tenant_id}`; the platform webhook can no longer touch a brand that has its own account.
- Console: Integrations → "Online payments — Razorpay" panel (connect / update / disconnect, webhook URL and setup steps).
- Storefront: `/storefront/resolve` returns `payments.online` + public `razorpay_key_id`; online methods are disabled with "Not offered by this store yet" when off; Checkout uses the brand's key and name.
- Decision (user): guests may pay online. Guest checkout offers UPI/cards/net banking; `POST /payments/razorpay/verify-guest` (signature-proven, guest orders only, rate limited).
- Verified live (dev, Razorpay test mode): guest order ORD-100010 paid by test net banking → PAID in DB; Northwind (no account) resolves `online: false`. Tests: 40 backend (new `tests/payments/test_brand_gateway.py`), 5 console.

### Step 9 — Email (SMTP) and merchant password reset (2026-11-11)

- Decision (user): generic SMTP. `email_outbox` table (migration `c9d3e1f5a7b2`): emails are queued inside the transaction that causes them, deduplicated by key, and delivered by the scheduler's `emails` job every 30 s with exponential backoff; FAILED after `EMAIL_MAX_ATTEMPTS`. Unset `SMTP_HOST` = emails wait, nothing is lost.
- Order confirmation to the customer once an order is a sale (same rule as the Sheets export: COD at placement, online once paid), from the brand's name with Reply-To the brand's contact email. Review requests now go by email (they were a no-op before).
- Merchant "Forgot password?": `POST /platform/auth/password/forgot` (same answer for unknown emails, rate limited) and `/password/reset` (single-use token stored as SHA-256, 1 hour, revokes every refresh token). Console screens `/forgot-password` and `/reset-password`.
- Verified live (dev): reset request and 3 order confirmations queued in the outbox; nothing sent (no SMTP configured). Tests: 8 email/reset backend tests + 2 console tests.
- Not verified: delivery through a real SMTP server — needs your SMTP account.

### Step 8 — Plans and billing (2026-11-11)

- Decision (user): Free (25 products, 1 team member, CliQ subdomain) / Starter ₹999 (500 products, 3, own domain) / Growth ₹2,999 (unlimited products, 10, Sheets export, AI studio + 200 credits); 14-day trial on a brand's first paid plan; prices editable by operators. Migration `d2e4f6a8b0c1` re-seeds plans; brands on the old trial plan or no plan move to Free; existing PRO (legacy, unlimited) brands — the operator's CliQ store — keep it.
- Enforced on the server: product limit (product create), team limit (adding members), custom domains, Sheets export, AI studio. A lapsed subscription (cancelled, unpaid > 7 days, unpaid trial) falls back to Free's limits; nothing is deleted.
- Billing (`app/subscriptions/billing.py`): Razorpay Subscriptions on the platform's account — checkout creates the subscription (with `start_at` for the trial), the console opens Razorpay Checkout, the signed result is verified (and the subscription's `notes.tenant_id` must match), webhooks `subscription.*` at `/api/v1/billing/razorpay/webhook` keep status/periods current and downgrade on cancel. Switching plans cancels the old subscription.
- Console: Plan & billing page (usage vs limits, plan cards, upgrade, cancel). Operator console: Plans tab (prices, limits, features) and a per-brand plan picker (audited).
- Tests: 8 backend billing/limit tests (Razorpay faked), console test. Not verified: a real Razorpay Subscriptions charge (needs your account with Subscriptions enabled).

### Step 10 — Marketing: consent, segments, campaigns, abandoned carts (2026-11-11)

- Consent: `users.marketing_opt_in` (+ timestamp, `marketing_email` for guests); guest checkout checkbox (only with an email), account-page toggle, `PATCH /auth/me`.
- Campaigns (`email_campaigns`, migration `e3f5a7b9c1d2`): draft → audience count → send to a segment (everyone subscribed / ordered within N days / never ordered / tag). Sent through the email outbox, one per customer, each with a signed one-click unsubscribe link (storefront `/unsubscribe` asks for a click, so link scanners change nothing).
- Abandoned carts: signed-in, opted-in customers with an idle (1–48 h) non-empty cart and no order since get one reminder (emails job).
- Console: Email campaigns page. Tests: 5 backend + 1 console.

### Step 11 — AI studio and lookbooks (2026-11-11)

- API on the existing job/credit services: `/admin/ai/credits`, `/admin/ai/jobs` (create with Idempotency-Key, list, get, cancel, retry), `/admin/ai/outputs/{id}/review` (approve copies the private result to a public storefront image and adds it to the product), `POST /api/v1/webhooks/fashn?token=` (payload untrusted; triggers a status poll).
- `ai-worker` (Celery worker + beat sweep) added to `docker-compose.prod.yml`; Caddy exposes the FASHN webhook path.
- Lookbooks: `/admin/looks` (cover uploaded to the store, up to 6 pinned products with x/y hotspots, publish/hide/archive) and public `/storefront/looks`; the runway home shows a brand's published looks, falling back to the built-in CliQ looks.
- Console: AI studio page (credits, generate, poll, approve/reject) and Lookbooks editor (click to pin).
- Tests: 6 AI API + 3 lookbook backend tests, 3 console tests. BLOCKED: real generation needs a FASHN API key (`AI_PROVIDER=fashn`, `FASHN_API_KEY`).

### Step 7 — End-to-end tests (2026-11-11)

- `e2e/` (Playwright, installed Google Chrome): guest COD purchase + public tracking, two-brand isolation (titles, resolve, unknown host page), merchant console sign-in → brand → Plan & billing → Orders (needs `E2E_MERCHANT_*`).

### Step 12 — Load test (2026-11-11)

- `loadtest/storefront_load.py` (httpx, no extra tools): concurrent shoppers resolve the store, list and open products, create guest carts, add items, price checkout. Never places orders.
- Dev baseline (laptop, 12 cores / 7.4 GB, API with **1** uvicorn worker, Postgres/Redis/MinIO and both Next dev servers on the same machine), 25 shoppers for 45 s:
  4,904 requests, **108 req/s, p50 196 ms, p95 377 ms, p99 521 ms, 0 errors**. Guest-cart creation hit the per-IP limit (30/window) as designed, since all load came from one IP.
- Not done: the same run against the production stack (`WEB_CONCURRENCY`/`API_WORKERS`=2+, Caddy, real TLS) — blocked with the prod rehearsal (disk space).

### Verification summary (2026-11-11, end of session)

- Backend: 1,634 tests passed in 17 folders + 6 AI tests, 0 failures. Console: 227/227 Vitest. Both frontends: `next build` succeeds. E2E: 4/4 against the dev stack. Dev database migrated to `e3f5a7b9c1d2` (backup `backend/var/backups/db-before-plans-marketing-*.dump`).

### Production rehearsal (2026-11-12)

Full `docker-compose.prod.yml` stack built and run locally (Caddy local CA). Bugs it found, now fixed:

1. **Every `python -m app.commands.*` failed** (`NoReferencedTableError`): commands did not load the model registry. `app/commands/__init__.py` now imports it; regression test `tests/core/test_commands_import.py` runs each command in a fresh process (10/12 failed before the fix).
2. **Bootstrap store unreachable**: bootstrap created no `stores` row (so no certificate for `<slug>.<root>`) and no plan. It now creates a published store and puts it on the legacy unlimited plan (tested).
3. **Product photos 500 in production**: the storefront's image optimizer fetched `media.<root>`, which inside a container resolves to itself. Caddy now has a `media.<root>` alias on the internal network; a local rehearsal additionally trusts Caddy's CA via `deploy/rehearsal.override.yml`.
4. `SEED_ADMIN_PHONE` is required by bootstrap; the template now says so.
5. E2E tests made robust for production builds (wait for hydration; on HTTPS an unknown host must get *no certificate*).

Verified: all services healthy; migrate-before-API; bootstrap; console signup → brand → publish → on-demand certificate; unknown hosts refused; API private routes 404 from outside; scheduler jobs ok (disk-space job correctly alerting at <10% free on this laptop); backup + restore drill on real data; E2E 4/4 over HTTPS; load test (see deployment.md): 0 errors up to 60 concurrent shoppers, ~120 req/s ceiling with 2 API workers on a laptop.

### Deployment readiness audit (2026-11-12)

Full findings, checklist, DNS, variables, rollback and acceptance tests are in
[`production-readiness.md`](production-readiness.md). Confirmed blockers it found, fixed and
verified on the rehearsal stack:

1. **Per-IP rate limits were shared by every shopper of a brand.** The storefront's server-side calls
   (guest checkout, payment confirmation, order tracking, search/collections, sign-in, token refresh)
   reached the API from the storefront container's address. In production the 11th guest order
   in a minute would have failed for everyone. The storefront now forwards the shopper's IP (taken from Caddy's
   `X-Forwarded-For`, which Caddy sets itself and does not accept from clients) on uncached calls.
   Rate-limit keys in Redis confirmed the shopper's address is now counted, and a spoofed header was ignored.
2. **Rollback after a migration could not start.** `alembic upgrade head` fails on a database a newer release
   migrated (`Can't locate revision`), so the old API never started. `migrate` now runs
   `app.commands.migrate`, which skips in that case and still fails on any real migration error (both verified).
3. **Container logs grew without limit** (about 2–3 GB/day at the load-test rate). Every service is now capped at 5 × 20 MB.
4. **The documented restore command could not run** (`$POSTGRES_USER` was expanded by the host shell, and the
   AI worker was left running). Corrected and verified: dump → restore → same row counts.
