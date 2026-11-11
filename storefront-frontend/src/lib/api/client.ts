import { apiBaseUrl } from '@/lib/env';
import { ApiError, ApiUnreachableError } from '@/lib/api/errors';
import type { ApiEnvelope, ApiErrorEnvelope, Page } from '@/types/api';

export type QueryValue = string | number | boolean | null | undefined;

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
  query?: Record<string, QueryValue>;
  body?: unknown;
  /**
   * Multipart payload for the endpoints that take a file. Sent as-is, with
   * no Content-Type header of our own so fetch can add the boundary.
   */
  formData?: FormData;
  /** Bearer token to send. Omit for the public storefront endpoints. */
  token?: string | null;
  headers?: Record<string, string>;
  /** Next fetch cache controls, for server-rendered catalogue pages. */
  cache?: RequestCache;
  revalidate?: number | false;
  tags?: string[];
  signal?: AbortSignal;
}

/**
 * Build a query string, dropping anything unset.
 *
 * Request models forbid unknown fields, so sending `?brand=undefined` is a
 * 422 rather than a no-op. Empty strings go too, since a blank search box
 * should mean "no filter" and not "match the empty string".
 */
function buildQuery(query: Record<string, QueryValue> | undefined): string {
  if (!query) return '';

  const params = new URLSearchParams();

  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') continue;
    params.set(key, String(value));
  }

  const encoded = params.toString();
  return encoded ? `?${encoded}` : '';
}

function isErrorEnvelope(body: unknown): body is ApiErrorEnvelope {
  return (
    typeof body === 'object' &&
    body !== null &&
    'error' in body &&
    typeof (body as { error: unknown }).error === 'object' &&
    (body as { error: unknown }).error !== null
  );
}

function retryAfterFrom(response: Response): number | null {
  const header = response.headers.get('Retry-After');
  if (!header) return null;

  const seconds = Number.parseInt(header, 10);
  return Number.isFinite(seconds) ? seconds : null;
}

/**
 * Send one request and return its envelope, or throw a normalised ApiError.
 *
 * Every success is `{success, message, data, meta}` and every failure is
 * `{success, message, error}`, so unwrapping and error normalisation happen
 * here once instead of at each call site. A 204 yields an empty envelope.
 *
 * The tenant is resolved by the backend from the request's Host header, so
 * there is deliberately no tenant header to attach.
 */
async function send<T>(path: string, options: RequestOptions): Promise<ApiEnvelope<T>> {
  const {
    method = 'GET',
    query,
    body,
    formData,
    token,
    headers = {},
    cache,
    revalidate,
    tags,
    signal,
  } = options;

  const url = `${apiBaseUrl()}${path}${buildQuery(query)}`;

  const requestHeaders: Record<string, string> = { Accept: 'application/json', ...headers };

  if (body !== undefined) {
    requestHeaders['Content-Type'] = 'application/json';
  }

  if (token) {
    requestHeaders.Authorization = `Bearer ${token}`;
  }

  const next: { revalidate?: number | false; tags?: string[] } = {};
  if (revalidate !== undefined) next.revalidate = revalidate;
  if (tags) next.tags = tags;

  let response: Response;

  try {
    response = await fetch(url, {
      method,
      headers: requestHeaders,
      body: formData ?? (body === undefined ? undefined : JSON.stringify(body)),
      signal,
      ...(cache ? { cache } : {}),
      ...(Object.keys(next).length ? { next } : {}),
    });
  } catch (cause) {
    throw new ApiUnreachableError(cause);
  }

  const requestId = response.headers.get('X-Request-Id');

  if (response.status === 204) {
    return { success: true, message: 'OK', data: null, meta: null };
  }

  let payload: unknown = null;

  try {
    payload = await response.json();
  } catch (cause) {
    if (response.ok) throw new ApiUnreachableError(cause);
  }

  if (!response.ok) {
    if (isErrorEnvelope(payload)) {
      throw new ApiError({
        status: response.status,
        code: payload.error.code,
        message: payload.message,
        details: payload.error.details,
        requestId: payload.error.request_id ?? requestId,
        retryAfterSeconds: retryAfterFrom(response),
      });
    }

    throw new ApiError({
      status: response.status,
      code: 'HTTP_ERROR',
      message: `Request failed with status ${response.status}`,
      requestId,
      retryAfterSeconds: retryAfterFrom(response),
    });
  }

  return payload as ApiEnvelope<T>;
}

/** Call the API and return the envelope's `data`. A 204 resolves to null. */
export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const envelope = await send<T>(path, options);
  return envelope.data as T;
}

/**
 * Call a listing endpoint, keeping the envelope's pagination meta.
 *
 * Listings answer with `data` as the rows and `meta` as the page counts;
 * both are needed to render a pager, so neither is discarded.
 */
export async function apiRequestPage<T>(
  path: string,
  options: RequestOptions = {},
): Promise<Page<T>> {
  const envelope = await send<T[]>(path, options);
  const items = envelope.data ?? [];

  return {
    items,
    meta: envelope.meta ?? {
      page: 1,
      page_size: items.length,
      total_items: items.length,
      total_pages: 1,
    },
  };
}
