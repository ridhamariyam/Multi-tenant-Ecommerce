import { vi } from "vitest";

type Handler = (url: URL, init: RequestInit) => { status?: number; body?: unknown; headers?: Record<string, string> } | undefined;

/** Replace fetch with a router: the first handler returning a response wins; unknown calls fail the test. */
export function mockFetch(...handlers: Handler[]) {
  const calls: { url: URL; init: RequestInit }[] = [];
  const fn = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = new URL(String(input));
    calls.push({ url, init });
    for (const h of handlers) {
      const r = h(url, init);
      if (r) {
        const text = r.body === undefined ? "" : typeof r.body === "string" ? r.body : JSON.stringify(r.body);
        return new Response(text, { status: r.status ?? 200, headers: r.headers });
      }
    }
    throw new Error(`Unexpected fetch ${init.method ?? "GET"} ${url.pathname}`);
  });
  vi.stubGlobal("fetch", fn);
  return { fn, calls };
}

export const ok = <T,>(data: T, meta: unknown = null) => ({ body: { success: true, message: "OK", data, meta } });

export const route = (method: string, path: string | RegExp, response: (url: URL, init: RequestInit) => ReturnType<Handler>): Handler =>
  (url, init) => {
    const m = (init.method ?? "GET") === method;
    const p = typeof path === "string" ? url.pathname === `/api/v1${path}` : path.test(url.pathname);
    return m && p ? response(url, init) : undefined;
  };

export const profile = (overrides: Record<string, unknown> = {}) => ({
  id: "u1",
  tenant_id: "t1",
  phone: "+919999999999",
  email: "staff@cliq.example",
  name: "Asha",
  role: "STAFF",
  status: "ACTIVE",
  is_verified: true,
  permissions: [],
  ...overrides,
});
