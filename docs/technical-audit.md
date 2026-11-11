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
| Password recovery, email verification for merchants | NOT IMPLEMENTED |
| Onboarding checklist, demo data | NOT IMPLEMENTED |
| Subscription plans / brand subscriptions | PARTIAL — models + service, **no API, no billing provider** |
| Credits / usage ledger | PARTIAL — models + service, no API |
| Virtual model library | PARTIAL — admin/brand API exists, no UI |
| AI try-on (FASHN) via Celery | PARTIAL — provider, job service, worker code exist; **no Celery worker in compose, no API, no UI**; BLOCKED (EXTERNAL) for live calls |
| Lookbooks | PARTIAL — models only |

### Infrastructure

| Item | Status |
|---|---|
| Backend image + healthchecks | IMPLEMENTED |
| Storefront / admin Docker images | NOT IMPLEMENTED |
| Reverse proxy, TLS, wildcard subdomains, custom-domain certs | NOT IMPLEMENTED |
| Celery worker / beat services | NOT IMPLEMENTED (scheduled jobs are shell `while sleep` loops) |
| CI pipeline | NOT IMPLEMENTED |
| Error monitoring (Sentry or similar), metrics | NOT IMPLEMENTED |
| Structured logging | PARTIAL — request ids exist; logs are plain text |
| Backups | MANUAL — `pg_dump` taken before each migration; no schedule, no restore drill |
| Staging / production configs | PARTIAL — one `.env`; `ENVIRONMENT` switch exists |
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
| R1 | Dev database was two migrations behind the code (fixed today; API 500'd on products after rebuild). There is no migrate-on-deploy step. | High (ops) |
| R2 | Storefront dependencies: 7 known vulnerabilities (`npm audit --omit=dev`): critical `swiper`, high `katex`/`postcss`, moderate `uuid`, `quill`. Admin: 0. | High |
| R3 | `NEXT_PUBLIC_SITE_URL` set in `.env` forces one site URL for every brand (canonical, sitemap). | Medium |
| R4 | Scheduled jobs are `while true; sleep` containers: no retries with backoff, no dead-letter, no monitoring. | Medium |
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
| 5 | Production deployment: storefront + admin Dockerfiles, reverse proxy with wildcard TLS, migrate-on-deploy, backup schedule + restore drill, env templates for staging/prod | Planned |
| 6 | Observability: structured JSON logs, error reporting hook (Sentry DSN optional), job health | Planned |
| 7 | E2E (Playwright): guest purchase, admin order handling, two-brand isolation | Planned |
| 8 | Subscriptions API + plan limits enforced server-side; billing provider integration | Planned (billing provider BLOCKED until chosen) |
| 9 | Merchant password reset + email provider adapter (transactional email) | Planned (provider BLOCKED until chosen) |
| 10 | Customer segments/consent, abandoned carts, campaigns | Planned |
| 11 | AI track: Celery worker service, try-on API + UI, credits API, lookbooks | Planned last (FASHN key BLOCKED) |
| 12 | Load test (k6 or Locust) against a production-like stack | Planned |

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
