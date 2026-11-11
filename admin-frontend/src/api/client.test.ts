import { describe, expect, it, vi } from "vitest";
import { mockFetch, ok, route } from "../test/fetchMock";
import { clearToken, getRefreshToken, getToken, saveTokens } from "../utils/storage";
import { API_BASE_URL, ApiError, apiUrl, request, setUnauthorizedHandler } from "./client";

describe("api client", () => {
  it("uses the admin origin for API requests so Next can proxy them without browser CORS", () => {
    expect(API_BASE_URL).toBe("/api/v1");
    expect(new URL(apiUrl("/admin/orders", { page: 2 })).origin).toBe(window.location.origin);
    expect(new URL(apiUrl("/admin/orders", { page: 2 })).pathname).toBe("/api/v1/admin/orders");
  });

  it("sends the bearer token and unwraps the envelope", async () => {
    saveTokens("access-1", "refresh-1");
    const { calls } = mockFetch(route("GET", "/admin/orders", () => ok([{ id: "o1" }], { page: 1 })));

    const response = await request<{ id: string }[]>("/admin/orders", { query: { status: "PENDING", empty: "" } });

    expect(response.data).toEqual([{ id: "o1" }]);
    expect((calls[0].init.headers as Record<string, string>).Authorization).toBe("Bearer access-1");
    expect(calls[0].init.cache).toBe("no-store");
    expect(calls[0].url.searchParams.get("status")).toBe("PENDING");
    expect(calls[0].url.searchParams.has("empty")).toBe(false);
  });

  it("refreshes an expired access token once and retries", async () => {
    saveTokens("old", "refresh-1");
    let attempts = 0;
    mockFetch(
      route("POST", "/auth/refresh", () => ok({ access_token: "new", refresh_token: "refresh-2" })),
      route("GET", "/auth/me", (_u, init) => {
        attempts++;
        const auth = (init.headers as Record<string, string>).Authorization;
        return auth === "Bearer new" ? ok({ id: "u1" }) : { status: 401, body: { message: "expired" } };
      })
    );

    const response = await request<{ id: string }>("/auth/me");

    expect(response.data.id).toBe("u1");
    expect(attempts).toBe(2);
    expect(getToken()).toBe("new");
    expect(getRefreshToken()).toBe("refresh-2");
  });

  it("signs out when the refresh token is rejected too", async () => {
    saveTokens("old", "bad");
    const onUnauthorized = vi.fn();
    setUnauthorizedHandler(onUnauthorized);
    mockFetch(
      route("POST", "/auth/refresh", () => ({ status: 401, body: { message: "no" } })),
      route("GET", "/auth/me", () => ({ status: 401, body: { message: "expired" } }))
    );

    await expect(request("/auth/me")).rejects.toBeInstanceOf(ApiError);
    expect(onUnauthorized).toHaveBeenCalled();
    expect(getToken()).toBeNull();
    setUnauthorizedHandler(null);
  });

  it("turns validation errors into one readable message", async () => {
    mockFetch(route("POST", "/admin/coupons", () => ({ status: 422, body: { message: "Invalid", error: { code: "VALIDATION_ERROR", details: [{ field: "code", message: "too long" }] } } })));

    await expect(request("/admin/coupons", { method: "POST", body: {} })).rejects.toMatchObject({
      message: "Invalid (code: too long)",
      status: 422,
      code: "VALIDATION_ERROR",
    });
  });

  it("explains server failures without exposing backend internals", async () => {
    mockFetch(route("GET", "/admin/dashboard", () => ({ status: 500, body: { message: "An unexpected error occurred" } })));

    await expect(request("/admin/dashboard")).rejects.toMatchObject({
      message: "The server could not load this data (HTTP 500). Try again, and contact your system administrator if the problem continues.",
      status: 500,
    });
  });

  it("shares refresh across concurrent requests and reuses new tokens for a delayed old 401", async () => {
    saveTokens("old", "refresh-1");
    let releaseLate!: (response: Response) => void;
    let releaseRefresh!: (response: Response) => void;
    const response = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status });
    const fetcher = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const path = new URL(String(input)).pathname;
      if (path.endsWith("/auth/refresh")) return new Promise<Response>((resolve) => { releaseRefresh = resolve; });
      if ((init.headers as Record<string, string>).Authorization === "Bearer new") return response(ok({ id: "u1" }).body);
      if (path.endsWith("/late")) return new Promise<Response>((resolve) => { releaseLate = resolve; });
      return response({ message: "expired" }, 401);
    });
    vi.stubGlobal("fetch", fetcher);
    const late = request("/late");
    const first = request("/auth/me");
    const second = request("/admin/orders");
    await vi.waitFor(() => expect(releaseRefresh).toBeTypeOf("function"));
    releaseRefresh(response(ok({ access_token: "new", refresh_token: "refresh-2" }).body));
    await Promise.all([first, second]);
    releaseLate(response({ message: "expired" }, 401));
    await late;
    expect(fetcher.mock.calls.filter(([input]) => String(input).endsWith("/auth/refresh"))).toHaveLength(1);
    expect(getRefreshToken()).toBe("refresh-2");
  });

  it("preserves tokens on temporary refresh failures and can retry later", async () => {
    saveTokens("old", "refresh-1");
    let unavailable = true;
    const onUnauthorized = vi.fn();
    setUnauthorizedHandler(onUnauthorized);
    mockFetch(
      route("POST", "/auth/refresh", () => unavailable ? { status: 503, body: { message: "Try later" } } : ok({ access_token: "new", refresh_token: "refresh-2" })),
      route("GET", "/auth/me", (_url, init) => (init.headers as Record<string, string>).Authorization === "Bearer new" ? ok({ id: "u1" }) : { status: 401 }),
    );
    await expect(request("/auth/me")).rejects.toMatchObject({ status: 503 });
    expect(getToken()).toBe("old");
    expect(getRefreshToken()).toBe("refresh-1");
    expect(onUnauthorized).not.toHaveBeenCalled();
    unavailable = false;
    await expect(request("/auth/me")).resolves.toMatchObject({ data: { id: "u1" } });
    setUnauthorizedHandler(null);
  });

  it("does not restore tokens after sign out during a pending refresh", async () => {
    saveTokens("old", "refresh-1");
    let complete!: (response: Response) => void;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => String(input).endsWith("/auth/refresh")
      ? new Promise<Response>((resolve) => { complete = resolve; })
      : new Response(JSON.stringify({ message: "expired" }), { status: 401 })));
    const pending = request("/auth/me");
    const rejected = expect(pending).rejects.toMatchObject({ status: 401 });
    await vi.waitFor(() => expect(complete).toBeTypeOf("function"));
    clearToken();
    complete(new Response(JSON.stringify(ok({ access_token: "new", refresh_token: "refresh-2" }).body)));
    await rejected;
    expect(getToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
  });
});
