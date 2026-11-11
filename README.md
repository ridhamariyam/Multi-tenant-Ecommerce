# CliQ. E-Commerce Platform

A full-stack commerce platform for **CliQ.**, a streetwear brand selling sneakers, tees and hoodies. It comprises a customer storefront, a staff admin panel and a multi-tenant REST API, with payments, phone sign-in, GST-aware checkout and courier fulfilment built in.

## Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Technology](#technology)
- [Getting started](#getting-started)
- [Running the applications](#running-the-applications)
- [Configuration](#configuration)
- [Testing and quality checks](#testing-and-quality-checks)
- [Background jobs](#background-jobs)
- [Deployment](#deployment)
- [Go-live checklist](#go-live-checklist)
- [Troubleshooting](#troubleshooting)
- [Further documentation](#further-documentation)

## Overview

| Application | Path | Purpose |
|---|---|---|
| Storefront | `storefront-frontend/` | Browsing, search, wishlist, cart, checkout, orders, invoices and customer accounts |
| Admin panel | `admin-frontend/` | Products, inventory, orders, customers, coupons, CMS, GST, COD, shipping, reports, staff and audit logs |
| API | `backend/` | Business logic, authentication, tenancy, integrations and data access |

**Integrations:** Razorpay (payments), MSG91 (phone OTP), Google Identity Services (optional sign-in) and Shiprocket (courier booking, labels and tracking).

## Architecture

```text
Storefront (Next.js)  ──┐
                        ├──▶  API (FastAPI)  ──▶  PostgreSQL 16
Admin panel (Next.js) ──┘          │         ──▶  Redis 7
                                   │
                                   └──▶  Razorpay · MSG91 · Google · Shiprocket
```

- **Tenancy:** each request is resolved to a tenant from its host name. In production that host must be registered in the `tenant_domains` table.
- **Customer sessions:** tokens are held in `httpOnly` cookies, and refresh tokens rotate on use.
- **Sign-in:** customers use a phone OTP or Google. Staff and admins use a password through separate routes.
- **Payments:** the browser never receives the Razorpay secret. The backend verifies each payment signature before marking an order paid.

## Technology

| Layer | Stack |
|---|---|
| Storefront | Next.js 15, React 19, TypeScript |
| Admin panel | Next.js 16, React 19, TypeScript |
| API | Python 3.12, FastAPI, async SQLAlchemy 2, Alembic |
| Data | PostgreSQL 16, Redis 7 |
| Tooling | Docker Compose, Make, Ruff, pytest, GitHub Actions |

## Getting started

### Prerequisites

- Docker with Docker Compose
- Python 3.12
- Node.js and npm
- Make and OpenSSL

### Setup

```bash
# 1. Create the environment file, then set your own secrets
cp .env.example .env

# 2. Install the backend tooling
python -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements-dev.txt

# 3. Start PostgreSQL, Redis and the API, and apply migrations
make dev

# 4. Create the CliQ. tenant, its domain and the admin user
docker compose exec api python -m app.commands.bootstrap
```

`bootstrap` adds no demo data and is safe in production, where the admin password must be at least 12 characters.

For a development catalogue, demo users and sample offers, run the seed instead. It refuses to run in production.

```bash
docker compose exec api python -m app.commands.seed
```

## Running the applications

Run these from the repository root.

| Command | Result | Address |
|---|---|---|
| `make dev` | PostgreSQL, Redis and the API | <http://localhost:58000/docs> |
| `npm run dev:storefront` | Storefront | <http://localhost:3000> |
| `npm run dev:admin` | Admin panel | <http://localhost:3001/admin> |
| `npm run dev:all` | Storefront and admin panel together | As above |

### Testing phone sign-in locally

Phone sign-in does not work on `localhost` or over plain HTTP. MSG91's hCaptcha check rejects `localhost`, and its encryption needs browser APIs that are only available on HTTPS.

1. Add `127.0.0.1 tws.test` to `/etc/hosts`.
2. Start the storefront over HTTPS:

   ```bash
   cd storefront-frontend
   npm run dev:https
   ```

3. Open <https://tws.test:3000> and accept the self-signed certificate warning.

## Configuration

All variables are described in [`.env.example`](.env.example). The frontends read `storefront-frontend/.env.local` and `admin-frontend/.env.local`; each has its own `.env.example`. Never commit real credentials.

| Area | Key variables |
|---|---|
| Core | `ENVIRONMENT`, `DATABASE_URL`, `REDIS_URL`, `CORS_ORIGINS` |
| Tokens | `JWT_SECRET`, `JWT_REFRESH_SECRET` |
| Bootstrap | `SEED_TENANT_*`, `SEED_ADMIN_*` |
| Razorpay | `RAZORPAY_ENVIRONMENT`, `SANDBOX_RAZORPAY_*`, `PRODUCTION_RAZORPAY_*`, `RAZORPAY_WEBHOOK_SECRET`, `NEXT_PUBLIC_RAZORPAY_KEY_ID` |
| MSG91 | `MSG91_AUTH_KEY`, `NEXT_PUBLIC_MSG91_WIDGET_ID`, `NEXT_PUBLIC_MSG91_TOKEN_AUTH` |
| Google (optional) | `GOOGLE_CLIENT_ID`, `NEXT_PUBLIC_GOOGLE_CLIENT_ID` |
| Shiprocket | `SHIPROCKET_*` |
| Storefront | `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_SITE_URL`, `NEXT_PUBLIC_CURRENCY` |
| Admin panel | `NEXT_PUBLIC_API_ORIGIN`, `NEXT_PUBLIC_STOREFRONT_URL`, `NEXT_PUBLIC_AUTH_IDLE_TIMEOUT_MINUTES` |

`RAZORPAY_ENVIRONMENT` selects the sandbox or production key pair. `NEXT_PUBLIC_RAZORPAY_KEY_ID` must be the key ID from the same pair. `NEXT_PUBLIC_*` values are built into the frontend, so rebuild after changing them.

In production, the API refuses to start with placeholder or short JWT secrets, or with a wildcard CORS origin.

## Testing and quality checks

| Command | What it does |
|---|---|
| `make test` | Runs the backend suite against a disposable PostgreSQL and Redis; never touches the application database |
| `make lint` | Runs Ruff |
| `make check` | Runs compile checks, lint, migration drift detection and tests |

`make test` needs Docker and a built API image. GitHub Actions also runs dependency vulnerability checks, migrations from an empty database, frontend type-checks and production builds.

## Background jobs

| Compose service | Interval | Purpose |
|---|---|---|
| `order-expiry` | 5 minutes | Expires unpaid online orders |
| `shipment-sync` | 15 minutes | Refreshes tracking for parcels that no webhook has updated |

## Deployment

Compose builds the API and both background jobs from `backend/`. The frontends have no Dockerfiles yet, so build them with `npm run build` and serve them with `npm start`, or host them on a Node-compatible platform.

**Every release must apply database migrations.** Nothing runs them automatically, and new code will fail against an older schema.

```bash
docker compose exec api alembic upgrade head
```

Back up the database first. Serve all applications over HTTPS, which phone sign-in requires.

## Go-live checklist

**Infrastructure**

- [ ] Domains and HTTPS configured for the storefront, admin panel and API
- [ ] API host registered in `tenant_domains`
- [ ] `ENVIRONMENT=production`, and new JWT secrets generated
- [ ] `CORS_ORIGINS` limited to the live origins
- [ ] `NEXT_PUBLIC_SITE_URL` and the API URLs set to live addresses
- [ ] Database backups scheduled, and a restore tested
- [ ] `order-expiry` and `shipment-sync` running

**Integrations**

- [ ] Live Razorpay keys set, with `RAZORPAY_ENVIRONMENT=production`
- [ ] Razorpay webhook created and `RAZORPAY_WEBHOOK_SECRET` set
- [ ] MSG91 widget and hCaptcha working on the live domain
- [ ] Shiprocket credentials, webhook token and booking setting configured
- [ ] Google client ID set, if Google sign-in is wanted

**Content and verification**

- [ ] Real products, prices, photos and stock loaded; test data removed
- [ ] Homepage rail images matched to real products
- [ ] Privacy, terms and shipping/returns text legally reviewed
- [ ] Legal business details, support email and social links added
- [ ] Seeded admin password changed
- [ ] Live test completed: real OTP sign-in, paid order, refund, cash-on-delivery order, shipment and return

## Troubleshooting

| Symptom | Cause | Resolution |
|---|---|---|
| Sign-in shows that HTTPS is needed, or no code arrives | Running on `localhost` or HTTP | Use `npm run dev:https` |
| "Online payment is not available right now" | Razorpay credentials not loaded | Check `RAZORPAY_ENVIRONMENT` and its key pair, then restart the API |
| Razorpay window fails to load | Storefront key is wrong or from another mode | Match `NEXT_PUBLIC_RAZORPAY_KEY_ID` to the API's key and rebuild |
| Order pages fail with a server error | Database schema is behind the code | Run `alembic upgrade head` |
| Browser reports a CORS error | Origin not allowed | Add it to `CORS_ORIGINS` and restart the API |

## Further documentation

- [Shiprocket integration guide](docs/shiprocket.md)
- Interactive API reference: <http://localhost:58000/docs> in development
