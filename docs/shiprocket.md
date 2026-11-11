# Shiprocket fulfilment

The integration extends the FastAPI / async SQLAlchemy backend, Alembic
migrations, the React admin, and the Next.js storefront.
Booking is disabled until server credentials are assigned to a tenant and that
tenant's administrator enables it in **Delivery → Shiprocket courier setup**.

## Architecture and integration points

- Checkout already computes configurable shipping, pincode overrides,
  free-shipping discounts, GST, COD fees and payment totals. It continues to
  persist that agreed total exactly once. Booking does not recalculate checkout.
- `app/shipments/provider.py` is the provider interface;
  `shiprocket.py` implements the official API; `service.py` handles booking,
  reconciliation, tracking and the existing order lifecycle.
- Shipment scans feed the existing customer order tracking history. Confirmed
  pickup / transit updates advance orders through `OrderService.update_status`,
  preserving stock fulfilment, COD collection and refund restrictions. Creating
  a booking or assigning an AWB does **not** mark an order shipped.
- The existing permission checks, audited admin routers and tenant predicates
  protect every administrative endpoint. Cross-tenant order requests return 404.
  Customer tracking contains no provider credentials, store costs or errors.
- `app.commands.sync_shipments` uses the existing command/Compose worker pattern;
  it needs the existing Redis token cache, with no new queue or subscription.

## Account and server setup

1. Create and verify a Shiprocket account, complete its business/KYC requirements,
   add a pickup address, and configure the couriers and wallet in the provider panel.
2. Create an **API user** in **Settings → API → Add New API User**. Use that user's
   email and password, rather than assuming the panel login is an API login.
3. Put secrets in the deployment's private environment or secret manager. The
   tracked `.env.example` contains placeholders only:

   ```dotenv
   SHIPROCKET_EMAIL=api-user@example.com
   SHIPROCKET_PASSWORD=replace-with-private-api-password
   SHIPROCKET_TENANT_ID=replace-with-the-stores-tenant-uuid
   SHIPROCKET_TENANT_CREDENTIALS={}
   SHIPROCKET_API_URL=https://apiv2.shiprocket.in/v1/external
   SHIPROCKET_WEBHOOK_TOKEN=replace-with-a-long-random-secret
   SHIPMENT_SYNC_INTERVAL_MINUTES=60
   ```

   Get the intended tenant UUID from `tenants.id` (matched to its store slug).
   Credentials without a matching `SHIPROCKET_TENANT_ID` cannot be used by any
   tenant. For multiple accounts, supply a server-only JSON map instead:

   ```dotenv
   SHIPROCKET_TENANT_CREDENTIALS={"tenant-uuid":{"email":"api@example.com","password":"private-secret"}}
   ```

   Each tenant's map entry uses its own account. These fields are never editable
   through the browser and must never use a `NEXT_PUBLIC_` prefix. Do not change
   an account binding while its shipments are active.
4. Apply migration `76034eb57569` before serving the new routes or starting sync:

   ```sh
   docker compose build api
   docker compose run --rm api alembic upgrade head
   docker compose up -d api shipment-sync
   ```

   With the complete local environment configured, the repository's normal
   `make dev` also applies migrations. Production rollouts should migrate before
   exposing the new application version.
5. In the admin **Delivery** page, load the registered pickup locations, select
   the correct warehouse, enter its origin pincode, and supply a fallback buyer
   email if phone-only orders need one. Configure measured package defaults if
   appropriate, then enable real bookings. Every order can override the defaults.

Optional backend settings: `SHIPROCKET_TIMEOUT_SECONDS` (default 20, maximum
120), `SHIPROCKET_READ_RETRIES` (default 2, maximum 5), and
`SHIPROCKET_TOKEN_TTL_SECONDS` (default nine days, must be below ten days).
Tokens are refreshed after expiry or one rejected authenticated request.
Changing the API password also changes the cache key.

## Webhooks and scheduled tracking

Register an HTTPS URL such as:

```text
https://api.your-store.example/api/v1/courier-webhooks/tracking
```

Configure the webhook security token in **Settings → API → Webhooks** to match
`SHIPROCKET_WEBHOOK_TOKEN`. Shiprocket sends it in the `x-api-key` header.
The handler compares it in constant time and refuses requests when no token is
configured. The provider documentation restricts webhook URLs containing
`shiprocket`, `kartrocket`, `sr` or `kr`; check the entire deployed URL.

Tracking events are deduplicated across webhook and poll delivery. Original
provider codes and payloads are retained even for unmapped statuses. Older
events and backward transitions do not regress shipment state. Webhook state
changes need a provider timestamp; polling can supply a current status snapshot.

The `shipment-sync` Compose service checks every 15 minutes for shipments whose
configured sync interval has elapsed. A cron deployment can run:

```sh
docker compose exec -T api python -m app.commands.sync_shipments
```

The worker refreshes tracking and looks up uncertain bookings. It never creates
new bookings automatically. The admin's **Refresh courier tracking** also works
for terminal shipments, allowing order synchronization to be retried.

## Order-to-shipment workflow

1. Confirm the order. Online payments must be captured; any required COD advance
   must be paid. Only valid Indian delivery addresses are supported.
2. Open the order's **Courier fulfilment** panel. Enter the actual packed parcel's
   weight in kg and dimensions in cm, or use explicitly configured defaults.
3. Check live courier rates, choose a courier if desired, and create the shipment.
   The confirmation books in the configured real account. Leaving the courier
   unselected lets the admin assign it after booking.
4. Assign an AWB, generate the courier label, schedule pickup, and generate or
   reprint the manifest. Label and manifest links open provider-hosted PDFs that
   can be downloaded or printed with the browser.
5. Pickup / in-transit scans advance the order; delivery collects only the unpaid
   COD balance through the existing payment workflow. Customers see the courier,
   AWB, official status, tracking link, provider estimate when supplied, and scans
   on their existing order-details page.
6. Cancel an eligible courier booking before changing the delivery address,
   editing manual tracking details, or cancelling the CliQ. order. Courier
   cancellation leaves the order and payment unchanged. A new booking gets a
   new reference and attempt number.

Internal states: `PENDING_FULFILMENT`, `SHIPMENT_CREATED`, `READY_TO_SHIP`,
`PICKUP_SCHEDULED`, `PICKED_UP`, `IN_TRANSIT`, `OUT_FOR_DELIVERY`, `DELIVERED`,
`DELIVERY_EXCEPTION`, `RETURN_TO_ORIGIN`, `RETURNED_TO_ORIGIN`, `CANCELLED`.
Exceptions may recover into a later verified delivery state; terminal states
and an established RTO journey cannot regress to the outbound journey.

### Failed or uncertain requests

Creating a shipment persists its unique reference and pending operation before
the provider call. A timeout, malformed success response, or server error records
an **unknown outcome**. **Retry / reconcile** looks up the existing booking by
the exact reference; an empty search result does not prove the first request
failed, so it never automatically resends an uncertain create or AWB assignment.
An uncertain pickup is checked through tracking rather than rescheduled blindly.

If reconciliation still finds nothing, use the reference displayed in the panel
to inspect Shiprocket or contact its support. Unresolved attempts deliberately
remain blocked from replacement booking. A definitive provider refusal can be
retried safely or cancelled locally. This conservative policy favors preventing
duplicate chargeable shipments over automatically clearing every failed attempt.

An order update rejected by the existing refund/payment rules appears as an
actionable shipment error. The original courier state is retained. RTO and courier
cancellation never initiate refunds. Follow the existing order/payment workflow.

## API and database

All paths below are under `/api/v1`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/admin/orders/{order_id}/shipments` | Current shipment, cancelled attempts, actions and booking eligibility |
| GET | `/admin/orders/{order_id}/shipments/rates` | Official courier quotes for the parcel; optional weight/dimension query fields |
| POST | `/admin/orders/{order_id}/shipments` | Book; optional `package` and `courier_id` |
| POST | `/admin/orders/{order_id}/shipments/{id}/awb` | Assign courier and AWB; optional `courier_id` |
| POST | `/admin/orders/{order_id}/shipments/{id}/pickup` | Schedule pickup; optional `pickup_date` |
| POST | `/admin/orders/{order_id}/shipments/{id}/label` | Generate label |
| POST | `/admin/orders/{order_id}/shipments/{id}/manifest` | Generate / reprint manifest |
| POST | `/admin/orders/{order_id}/shipments/{id}/sync` | Refresh tracking and retry order synchronization |
| POST | `/admin/orders/{order_id}/shipments/{id}/cancel` | Cancel courier booking |
| POST | `/admin/orders/{order_id}/shipments/{id}/retry` | Recover the last unfinished operation |
| GET, PUT | `/admin/shipping/provider` | Read / save tenant provider settings |
| GET | `/admin/shipping/provider/pickup-locations` | List locations belonging to this tenant's configured account |
| POST | `/courier-webhooks/tracking` | Authenticated provider tracking callback |

Existing authenticated customer tracking endpoints gain an optional `courier`
object. Customers continue using their existing order APIs and ownership checks.
Shipment mutations require `orders.manage`; reads require `orders.view`.
Provider settings require `settings.view` / `settings.manage`.

Migration `76034eb57569`, parent `f1526859bb6a`, adds:

- `shipping_provider_settings`: tenant enablement, pickup details, fallback email
  and optional complete package defaults; no credentials in the database.
- `shipments`: tenant/order composite foreign key, provider IDs, unique booking
  reference and AWB, package, COD amount, quoted freight/COD charges, current
  state, pending operation, error/retry data and lifecycle timestamps. A partial
  unique index allows at most one non-cancelled booking per tenant/order.
- `shipment_events`: tenant/shipment composite foreign key, original provider
  payload, timestamp and deduplication key, plus mapped state and scan details.

Primary files: `backend/app/shipments/*`, `backend/app/commands/sync_shipments.py`,
the migration, order service/schema/router/serializer changes, provider config,
model and router registration, integration status, `.env.example`, Compose worker,
`admin-frontend/src/api/shipments.ts`, `types/shipment.ts`, `ShipmentPanel.tsx`,
`ProviderSettings.tsx`, `ParcelFields.tsx`, and the storefront order-details types,
page and component. Tests live in `backend/tests/shipments/test_unit.py`,
`backend/tests/orders/test_shipments.py`, and the two new admin component test files.

## Validation and limits

Automated provider tests use `httpx.MockTransport`; service recovery tests and UI
tests use fakes. No real shipment is booked by any test. Run the fast backend checks:

```sh
cd backend
python -m unittest tests.shipments.test_unit -v
```

Run database-backed shipping and existing order/payment regressions against the
repository's throwaway PostgreSQL/Redis containers:

```sh
backend/scripts/test.sh tests/orders tests/payments tests/admin/test_integrations.py
```

Executed successfully in this work session:

- 47 shipping provider, recovery, state, credential-scope and amount-snapshot unit
  tests, plus two existing Razorpay safety unit tests (49 total).
- The complete admin suite: 204 tests across 38 files, including nine new shipping
  UI tests. Run with `--maxWorkers=1 --testTimeout=20000` in constrained environments;
  an initial highly concurrent run timed out, and the serial rerun passed.
- TypeScript checks for both frontends; ESLint for changed admin files; backend
  Ruff and compilation checks; OpenAPI generation for all 12 shipping paths.
- Alembic reports one head, `76034eb57569`. Offline SQL generation from its parent
  succeeds: `python -m alembic upgrade f1526859bb6a:head --sql`.
- The 12 database integration tests collect successfully. They exercise booking,
  totals, retries, labels, pickup, manifests, delivery/COD, cancellation, RTO and
  authorization through the existing checkout and order fixtures.

Docker and server sockets are denied in the sandbox, so applying the migration,
checking migration drift against PostgreSQL, and executing database integration
tests still require the normal development environment before deployment. Full
history offline generation also encounters a pre-existing data backfill that
requires a live database; the new migration's parent-to-head SQL is validated.
No live credential verification, courier booking or webhook delivery was attempted.

Known limits:

- Checkout uses the existing configured delivery policy, rather than claiming
  to display a live courier quote. Freight/COD quotes in the admin are distinct
  from the customer shipping charge, final provider billing and COD settlement.
  Provider taxes, surcharges and weight adjustments may change final costs.
- One parcel per order, domestic India, one active provider per tenant. Split
  fulfilment, international shipping, automatic COD remittance reconciliation,
  and customer return-pickup booking are outside this implementation.
- Returns follow existing CliQ. rules. No new refund, paid notification or reverse
  logistics service is introduced. Paid RTO orders may require manual resolution
  when the existing refund workflow refuses the order transition.
- Credentials are server environment secrets, not an administrator-editable
  database secret store. Multiple tenants use explicitly assigned accounts.
- The official documentation does not establish a general public sandbox host.
  Credentials described as sandbox credentials must not be assumed to prevent
  real bookings. Use mocks until Shiprocket confirms the account/environment.
- Normal Shiprocket account, wallet, courier, COD, RTO and optional insurance
  charges still apply. There is no additional queue or notification subscription.

API paths, request shapes, token lifetime and webhook authentication were checked
against the [official Shiprocket API documentation](https://apidocs.shiprocket.in/)
and its Postman collection (`8407119/SzYW1zB2`, the collection retrieved during
the original implementation). The documentation page is a JavaScript shell;
the current collection could not be re-fetched from this restricted session.
