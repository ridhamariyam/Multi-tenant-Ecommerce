# Multi-brand platform: audit, architecture and progress

This document tracks the evolution of the CliQ. store into a multi-brand AI
fashion commerce platform. It starts with the audit of the existing code
(Phase 1), records the decisions taken, and describes what each finished phase
added. Phases not marked done have not been built yet.

| Phase | Scope | Status |
|---|---|---|
| 1 | Audit of the existing code | Done |
| 2 | Multi-tenant database foundation | Done |
| 3 | Brand registration and membership | Done (API; dashboard UI not yet) |
| 4 | Tenant authorization and security tests | Done |
| 5 | Product management on S3 (MinIO locally) | Done (API; admin UI still uploads through the API, which now writes to S3) |
| 6 | Store configuration and resolution | Partly: API and host resolution done, `GET /storefront/resolve` and frontend not yet |
| 7–15 | Character library, FASHN, Celery, AI Studio, lookbooks, storefronts, checkout, credits, E2E | Not started |

---

## 1. Audit of the existing code (Phase 1)

### Existing architecture

- **Backend:** FastAPI modular monolith (`backend/app/<module>/{models,schemas,repository,service,router}.py`),
  SQLAlchemy 2 async on asyncpg, Pydantic v2, Alembic (49 revisions before this work),
  Redis for caching and rate limits. Uniform `ApiResponse` envelope and typed error codes
  (`app/core/error_codes.py`).
- **Multi-tenancy already existed.** A `Tenant` is one store. 53 of 56 tables carry
  `tenant_id`, with 58 composite foreign keys (`(tenant_id, x_id) → (tenant_id, id)`) so a
  row can only point at rows of the same tenant. The tenant is resolved from the request
  hostname (`tenant_domains`). The test suite (1,492 tests) already checks one tenant
  against another ("Zeen" and "Acme" fixtures). Row-level security is not enabled.
- **Users are per tenant.** Every `users` row (customer, staff or admin) belongs to one
  tenant; tokens carry `tenant_id` and must match the host. A person in two stores has two
  logins. Admin permissions are a fixed enum (`app/auth/permissions.py`).
- **Commerce:** catalogue (products, options, variants, inventory and movements, images),
  cart, checkout with idempotency keys, orders with price/name snapshots on order items,
  Razorpay payments (platform-wide keys), COD, coupons, GST pricing, Shiprocket shipments,
  returns, reviews, wishlists, CMS, reports, audit log.
- **Storage:** `app/core/storage.py` has a `Storage` protocol with one implementation,
  local disk served at `/media`. Uploads go through the API (no presigned URLs).
- **Background work:** no task queue. Two loop containers run commands every few minutes
  (order expiry, shipment sync).
- **Frontends:** `storefront-frontend` (Next.js 15, App Router) and `admin-frontend`
  (React 19 + Vite + React Router, Vitest tests).
- **Infrastructure:** Docker Compose with Postgres 16, Redis 7, the API and the two loop
  workers. No Nginx.

### Reusable as is
Tenant isolation and composite keys; the catalogue, cart, checkout, order, payment and
inventory modules; the permission system; the response and error conventions; the rate
limiter; the storage seam; the test harness (throwaway Postgres and Redis per run).

### Missing
Platform-level identity (one person, many brands); brand membership and roles; a store
entity with publication and subdomain; custom domain verification; platform
administration; object storage with presigned uploads; a task queue; the virtual
character library; AI generation; lookbooks; subscription plans and credit accounting.

### Decisions

1. **A brand is the existing `Tenant`.** No parallel `brands` table: every brand-owned
   table already keys on `tenant_id`, and duplicating it would split the isolation model.
2. **Merchant logins are platform-wide; shopper logins stay per brand.** Chosen with the
   owner (2026-11-06). A `merchant_accounts` row is the person; `brand_members` links it to
   each brand and to that brand's own ADMIN/STAFF `users` row. Customers of one brand stay
   unknown to every other brand.
3. **No change to the existing admin API.** A merchant exchanges the platform session for
   a short-lived *brand token*, which is an ordinary access token for the brand's user row
   plus a membership id. Every existing admin endpoint, permission check, audit entry and
   CMS authorship works unchanged.
4. **MinIO locally for S3** (chosen with the owner). Same API as S3, so presigned uploads
   and private buckets run for real in development.
5. **Row-level security deferred.** Isolation is enforced by tenant-scoped queries and
   composite keys today; RLS needs a per-transaction `SET app.tenant_id` across every
   session and a non-owner database role. It is planned as defence in depth, not as the
   primary control.

### Migration risks and how they were handled
- *Existing logins:* backfilled into merchant accounts with the same password hash, so
  people sign in to the platform with the password they already use. The per-store admin
  login keeps working.
- *Existing store going offline:* every existing tenant gets a store that is already
  published; existing domains are marked verified.
- *Staff phone rule:* `users.phone_is_e164` required a phone for staff. It is relaxed to
  "absent, or valid E.164" for members who sign in by email. Downgrade restores the strict
  rule as `NOT VALID`, so no rows are deleted.
- Tested against a copy of the development database: upgrade, `alembic check`, downgrade
  (users and orders intact), upgrade again.

---

## 2. Data model added in Phases 2–3

```
merchant_accounts (platform-wide person)
  id, email (unique, lowercase), name, phone, password_hash, status, is_platform_admin, last_login_at
merchant_refresh_tokens
  id, account_id → merchant_accounts, token_hash (unique), expires_at, revoked_at, replaced_at

tenants (= brands)  + status, description, logo_url, contact_email, phone,
                      owner_account_id → merchant_accounts, suspended_at, suspension_reason
brand_members
  id, tenant_id → tenants, account_id → merchant_accounts,
  (tenant_id, user_id) → users(tenant_id, id)       -- the member's ADMIN/STAFF row, same brand
  role  OWNER | ADMIN | PRODUCT_MANAGER | ORDER_MANAGER | CUSTOM
  status ACTIVE | REMOVED
  unique (tenant_id, account_id), unique (tenant_id, user_id), one active OWNER per brand
stores
  id, tenant_id (unique: one store per brand), name, subdomain (unique, DNS label),
  theme, logo_url, favicon_url, primary_color, secondary_color, published, published_at
tenant_domains (= store domains)  + verified_at, is_primary (one per brand), verification_token
```

Role → existing admin access (`app/brands/constants.py`):

| Membership role | `users.role` | Permissions |
|---|---|---|
| OWNER, ADMIN | ADMIN | everything |
| PRODUCT_MANAGER | STAFF | catalogue, CMS, reviews, coupons (view), dashboard |
| ORDER_MANAGER | STAFF | orders, customers, payments, catalogue (view), dashboard |
| CUSTOM | STAFF | whatever was set on the staff screen (migrated staff) |

Only OWNER and ADMIN manage the brand profile, members, store and domains.

## 3. How a request finds its brand

`app/tenants/resolver.py`, in order:

1. **Brand token.** An access token with a membership claim (`mbr`). The membership, its
   account and its brand are loaded on every request and must all be active, and the
   token's user and brand must match the membership. Removing a member or suspending a
   brand takes effect on the next request, not at token expiry. A brand id supplied by the
   client is never used.
2. **Hostname.** A verified domain in `tenant_domains`, or `<subdomain>.<PLATFORM_ROOT_DOMAIN>`.
   An unpublished store is only reachable with a staff token of that same brand.
3. **Development only:** `localhost` and loopback addresses fall back to the seed tenant.

Token types are separate: a platform session (`merchant_access`) is refused by every
brand endpoint, and a brand token is refused by the platform endpoints.

## 4. API added

All under `/api/v1`, using the existing response envelope.

| Method | Path | Who | What |
|---|---|---|---|
| POST | `/platform/auth/register` | anyone | Create a merchant account, returns a platform session |
| POST | `/platform/auth/login` | anyone | Sign in (rate-limited per IP and email) |
| POST | `/platform/auth/refresh` | session | Rotate the refresh token; reuse revokes the family |
| POST | `/platform/auth/logout` | session | Revoke a refresh token |
| GET | `/platform/auth/me` | session | The signed-in account |
| POST | `/brands/register` | session | Create brand + owner membership + admin row + store + default settings, one transaction; returns a brand token |
| GET | `/brands/me` | session | Brands the account belongs to |
| GET / PUT | `/brands/{brand_id}` | member / owner-admin | Brand profile |
| POST | `/brands/{brand_id}/switch` | member | A brand token for that brand |
| GET / POST | `/brands/{brand_id}/members` | member / owner-admin | List, or add an existing account with a role |
| PATCH | `/brands/{brand_id}/members/{member_id}` | owner-admin | Change role or remove (owner cannot be changed) |
| GET / PUT | `/brand/store` | brand token, owner-admin | Store settings |
| POST | `/brand/store/publish` | brand token, owner-admin | Publish or unpublish |
| GET / POST | `/brand/domains` | brand token, owner-admin | Custom domains (added unverified) |
| DELETE | `/brand/domains/{domain_id}` | brand token, owner-admin | Remove a domain |
| GET | `/platform/admin/brands` | platform admin | All brands, searchable, paginated |
| POST | `/platform/admin/brands/{id}/suspend` / `activate` | platform admin | Suspend or reinstate |
| POST | `/platform/admin/domains/{id}/verify` | platform admin | Approve a custom domain |

A brand the account is not a member of answers 404, the same as one that does not exist.

## 5. Running it

```bash
# Apply the migration (back up first in any shared environment)
docker compose exec api python -m alembic upgrade head

# Make someone a platform administrator (no API can do this)
docker compose exec api python -m app.commands.platform_admin grant you@example.com

# Tests
backend/scripts/test.sh tests/brands          # platform, brands, isolation, stores
backend/scripts/test.sh                       # everything
```

New settings (`.env`): `PLATFORM_ROOT_DOMAIN` (default `localhost`, so stores answer at
`<subdomain>.localhost`), `STOREFRONT_URL_TEMPLATE`, `MERCHANT_ACCESS_TOKEN_EXPIRE_MINUTES`,
`MERCHANT_REFRESH_TOKEN_EXPIRE_DAYS`, `BRAND_TOKEN_EXPIRE_MINUTES`.

## 6. File storage (Phase 5)

`app/core/storage.py` picks the backend from `STORAGE_BACKEND`:

- `local` (the old behaviour): files on the API's disk, served at `/media`.
- `s3`: an S3 bucket. In development that is the `minio` compose service
  (`bitnamilegacy/minio:2025.5.24`; MinIO stopped publishing images on Docker Hub, and this
  is the Bitnami build of the same server). API on `localhost:59000`, console on
  `localhost:59001`. Data in the `tws_ec2_minio_data` volume.

Bucket layout and access:

| Key | Who can read it |
|---|---|
| `<tenant_id>/<hex>.<ext>` | anyone (validated images; `Cache-Control: immutable`) |
| `pending/<tenant_id>/<hex>` | nobody but the API; deleted after 1 day by a lifecycle rule |

The bucket, its policy and the lifecycle rule are created at API startup when
`S3_CREATE_BUCKET=true` (`S3Storage.ensure_bucket`, idempotent). In production create them
once and leave the flag off.

### Direct (presigned) uploads

```
1. POST /catalogue/images/presign  {content_type, size_bytes}
      -> {upload_id, url, fields, expires_at, max_bytes}
2. Browser: POST multipart to `url` with every entry of `fields`, then the file as `file`
3. POST /catalogue/images/complete {upload_id}                       -> {url}
   or POST /catalogue/products/{id}/images/complete {upload_id, alt_text, sort_order, is_primary}
```

- The presigned POST policy fixes the exact key, the content type and a size of
  1..`MAX_UPLOAD_BYTES`, and expires after `S3_PRESIGN_EXPIRE_SECONDS` (default 10 min).
  Changing the key or type is refused by storage itself (tested).
- Nothing the browser sent is trusted. Completion reads the object back, decodes it with
  Pillow (same checks as the API upload: real JPEG/PNG/WebP, pixel limit), names it after
  its real format, copies it to a public key and deletes the pending object. A non-image
  is deleted and answers 400.
- `upload_id` must be a pending key of the caller's own brand; anything else, including
  another brand's id, answers 404. Completing twice answers 404 the second time; two at
  once write the same final key, so they cannot create two objects.
- Needs `CATALOGUE_MANAGE`; presign is limited to 120 per minute per user.
- With `STORAGE_BACKEND=local` presign answers 409 and points to `/catalogue/images/upload`.

The existing multipart endpoints (`/catalogue/images/upload`,
`/products/{id}/images/upload`, CMS and review photos) are unchanged for callers and now
store into whichever backend is configured. Storage being unreachable answers 503.

Settings: `STORAGE_BACKEND`, `S3_BUCKET`, `S3_REGION`, `S3_ACCESS_KEY_ID`,
`S3_SECRET_ACCESS_KEY`, `S3_ENDPOINT_URL` (how the API reaches storage; unset = AWS),
`S3_PRESIGN_ENDPOINT_URL` (how a browser reaches it; used for signing and image URLs),
`S3_PUBLIC_BASE_URL` (optional CDN), `S3_PRESIGN_EXPIRE_SECONDS`,
`S3_PENDING_RETENTION_DAYS`, `S3_CREATE_BUCKET`. Moving to AWS is a settings change: unset
the two endpoint URLs and supply real keys.

Tests: `backend/scripts/test.sh` starts a throwaway MinIO next to Postgres and Redis;
`tests/catalogue/test_presigned_uploads.py` runs against it (skipped if the image is absent).

## 7. Known limitations so far

- Images uploaded before the switch keep their `/media/...` URLs, still served by the API
  from the `tws_ec2_uploads_data` volume. They have not been copied into the bucket.
- The admin frontend still uploads through the API; switching it to presigned uploads is
  frontend work for a later phase.
- Removing a product image does not delete its file from storage (it did not before
  either); orphaned files need a sweep job once Celery exists.

- Adding a member needs the person to have signed up already; there are no email invitations.
- Custom domains are verified by a platform admin; the TXT record is generated but not
  checked automatically.
- One store per brand (enforced by a unique constraint, liftable later).
- Row-level security is not enabled (see decision 5).
- The existing per-store admin login (`/admin/auth/login` on a store's host) still works for
  logins that predate memberships. It does not see memberships, so it is a compatibility
  path, not the recommended one.
