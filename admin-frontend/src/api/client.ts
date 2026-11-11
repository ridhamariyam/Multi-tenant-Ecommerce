// The single place that talks HTTP to the backend.
// Every api/*.ts file goes through `request` (or `download`), so auth headers,
// token refresh, JSON handling and error messages work the same everywhere.

import type { ApiErrorDetail, ApiResponse } from "../types/api";
import { clearToken, getRefreshToken, getToken, saveTokens } from "../utils/storage";

// The backend resolves the store (tenant) from this host, so it must be the
// CliQ API's own domain in production. Configure with NEXT_PUBLIC_API_ORIGIN.
export const BACKEND_ORIGIN: string =
  process.env.NEXT_PUBLIC_API_ORIGIN ?? "http://localhost:58000";
// Browser requests stay same-origin; Next rewrites /api/v1 to BACKEND_ORIGIN.
// This avoids relying on the backend's CORS allowlist for the separate admin app.
export const API_BASE_URL = "/api/v1";

// The customer website, for "View on website" links. Optional (NEXT_PUBLIC_STOREFRONT_URL).
export const STOREFRONT_ORIGIN: string | null = process.env.NEXT_PUBLIC_STOREFRONT_URL ?? null;

export class ApiError extends Error {
  status: number;
  code: string | null;
  details: ApiErrorDetail[];

  constructor(message: string, status: number, details: ApiErrorDetail[] = [], code: string | null = null) {
    super(message);
    this.status = status;
    this.details = details;
    this.code = code;
  }
}

type QueryValue = string | number | boolean | null | undefined;

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  query?: object;
  body?: unknown; // sent as JSON
  formData?: FormData; // sent as multipart/form-data (file uploads)
  auth?: boolean; // false for the login calls themselves
}

let unauthorizedHandler: (() => void) | null = null;

/** Called when the session can no longer be used (refresh failed too). */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  unauthorizedHandler = handler;
}

export function apiUrl(path: string, query?: object): string {
  const url = new URL(
    `${API_BASE_URL}${path}`,
    typeof window === "undefined" ? "http://localhost" : window.location.origin,
  );
  if (query) {
    for (const [key, value] of Object.entries(query as Record<string, QueryValue>)) {
      if (value !== undefined && value !== null && value !== "") {
        url.searchParams.set(key, String(value));
      }
    }
  }
  return url.toString();
}

// Turns the backend error envelope into one readable sentence.
function errorFromBody(status: number, body: unknown): ApiError {
  const data = (body ?? {}) as {
    message?: string;
    detail?: unknown;
    error?: { code?: string; details?: ApiErrorDetail[] };
  };
  const details = data.error?.details ?? [];
  let message =
    data.message || (typeof data.detail === "string" ? data.detail : "") || `HTTP ${status}`;

  if (status >= 500 && (!message || message === "An unexpected error occurred")) {
    message = `The server could not load this data (HTTP ${status}). Try again, and contact your system administrator if the problem continues.`;
  }

  if (details.length > 0) {
    const fieldErrors = details
      .map((detail) => (detail.field ? `${detail.field}: ${detail.message}` : detail.message))
      .join("; ");
    message = `${message} (${fieldErrors})`;
  }
  return new ApiError(message, status, details, data.error?.code ?? null);
}

let refreshing: { token: string; promise: Promise<boolean> } | null = null;

/** Rotate once per session, including requests from other tabs when Web Locks are available. */
async function refreshSession(accessToken: string | null): Promise<boolean> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;
  if (refreshing?.token === refreshToken) return refreshing.promise;

  const rotate = async (): Promise<boolean> => {
    // Another request/tab may already have rotated or signed out while we waited.
    if (getToken() !== accessToken || getRefreshToken() !== refreshToken) return !!getToken();
    let response: Response;
    try {
      response = await fetch(apiUrl("/auth/refresh"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
    } catch {
      throw new ApiError("Unable to renew your session. Check your connection and try again.", 0);
    }
    // Do not replace a session that was signed out or changed during the request.
    if (getRefreshToken() !== refreshToken) return !!getToken();
    if (response.status === 401 || response.status === 403) return false;
    const json = await parse(response);
    if (!response.ok) throw errorFromBody(response.status, json);
    const tokens = (json as { data?: { access_token?: unknown; refresh_token?: unknown } } | null)?.data;
    if (typeof tokens?.access_token !== "string" || !tokens.access_token || typeof tokens.refresh_token !== "string" || !tokens.refresh_token) {
      throw new ApiError("Unable to renew your session. Please try again.", 502);
    }
    if (getRefreshToken() !== refreshToken) return !!getToken();
    saveTokens(tokens.access_token, tokens.refresh_token);
    return true;
  };
  const promise = typeof navigator !== "undefined" && navigator.locks
    ? navigator.locks.request("cliq-admin-session-refresh", rotate)
    : rotate();
  const pending = { token: refreshToken, promise };
  refreshing = pending;
  try { return await promise; }
  finally { if (refreshing === pending) refreshing = null; }
}

async function send(path: string, options: RequestOptions, retry: boolean): Promise<Response> {
  const { method = "GET", query, body, formData, auth = true } = options;
  const headers: Record<string, string> = {};
  const accessToken = auth ? getToken() : null;
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  let requestBody: BodyInit | undefined;
  if (formData) {
    requestBody = formData; // the browser sets the multipart boundary
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    requestBody = JSON.stringify(body);
  }

  let response: Response;
  try {
    response = await fetch(apiUrl(path, query), {
      method, headers, body: requestBody,
      // Workspace refresh must read current authenticated data, not a cached response.
      cache: auth && method === "GET" ? "no-store" : undefined,
    });
  } catch {
    throw new ApiError(
      "Could not reach the backend. Check your connection and try again.",
      0
    );
  }

  if (response.status === 401 && auth) {
    if (retry) {
      // A late 401 for the previous token must reuse the already renewed session.
      if (getToken() && getToken() !== accessToken) return send(path, options, false);
      if (await refreshSession(accessToken)) return send(path, options, false);
    }
    if (getToken() === accessToken) {
      clearToken();
      unauthorizedHandler?.();
    }
  }
  return response;
}

async function parse(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return { message: text };
  }
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<ApiResponse<T>> {
  const response = await send(path, options, true);
  const json = await parse(response);
  if (!response.ok) throw errorFromBody(response.status, json);
  // 204 No Content (archive/delete endpoints) has no body.
  return (json ?? { success: true, message: "Done", data: null, meta: null }) as ApiResponse<T>;
}

/**
 * Every row of a paginated listing: page 1, then the rest four requests at a time.
 * Throws if rows were added or removed while paging, so totals are never built on a partial list.
 */
export async function fetchAllPages<T extends { id: string }>(
  fetchPage: (page: number) => Promise<ApiResponse<T[]>>,
  what: string
): Promise<ApiResponse<T[]>> {
  const first = await fetchPage(1);
  const meta = first.meta;
  if (!meta) throw new Error(`The ${what} list cannot be paged. Refresh to try again.`);
  const pages = [first.data];
  for (let page = 2; page <= meta.total_pages; page += 4) {
    const batch = await Promise.all(
      Array.from({ length: Math.min(4, meta.total_pages - page + 1) }, (_, offset) => fetchPage(page + offset))
    );
    pages.push(...batch.map((result) => result.data));
  }
  const rows = pages.flat();
  if (rows.length !== meta.total_items || new Set(rows.map((row) => row.id)).size !== rows.length) {
    throw new Error(`The ${what} changed while loading. Refresh to try again.`);
  }
  return { ...first, data: rows, meta: null };
}

/** Fetch a file (PDF/CSV/XLSX) with the session and hand it to the browser as a download. */
export async function download(
  path: string,
  query?: object,
  fallbackName = "download",
  options: Pick<RequestOptions, "method" | "body"> = {}
): Promise<void> {
  const response = await send(path, { query, ...options }, true);
  if (!response.ok) throw errorFromBody(response.status, await parse(response));
  const disposition = response.headers.get("content-disposition") ?? "";
  const match = /filename="?([^";]+)"?/.exec(disposition);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = match?.[1] ?? fallbackName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Revoked on the next tick: some browsers cancel a download whose URL is freed straight away.
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

// Uploaded images come back as "/media/..." -- make them loadable from this app.
export function mediaUrl(url: string): string {
  return url.startsWith("/") ? `${BACKEND_ORIGIN}${url}` : url;
}
