# End-to-end tests

Browser tests against a **running** stack (development or staging). They use
the installed Google Chrome (`E2E_BROWSER_CHANNEL=chromium` after
`npx playwright install chromium` to use Playwright's own).

```sh
cd e2e && npm install
# dev defaults: storefront :3000, console :3001/admin, second brand at northwind.localhost:3000
E2E_MERCHANT_EMAIL=... E2E_MERCHANT_PASSWORD=... npm test
```

| Variable | Default |
|---|---|
| `E2E_STORE_URL` | `http://localhost:3000` |
| `E2E_SECOND_STORE_URL` / `E2E_SECOND_BRAND_NAME` | `http://northwind.localhost:3000` / `Northwind` |
| `E2E_CONSOLE_URL` | `http://localhost:3001/admin` |
| `E2E_MERCHANT_EMAIL` / `E2E_MERCHANT_PASSWORD` | unset: the console test is skipped |

They create real (test) orders in the target database: never point them at production.
