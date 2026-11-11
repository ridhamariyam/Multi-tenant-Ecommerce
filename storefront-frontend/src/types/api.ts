/**
 * Wire types for the CliQ API.
 *
 * Field names mirror the backend's snake_case exactly so a schema and its
 * type can be compared line by line. Money is a string, not a number: the
 * backend serialises Decimal as a JSON string, and parsing it into a float
 * would lose the precision the prices are stored with.
 */

export interface PageMeta {
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
}

export interface ApiEnvelope<T> {
  success: boolean;
  message: string;
  data: T | null;
  meta: PageMeta | null;
}

export interface ApiErrorDetail {
  field: string;
  type: string;
  message: string;
}

export interface ApiErrorPayload {
  code: string;
  details: ApiErrorDetail[];
  request_id: string | null;
}

export interface ApiErrorEnvelope {
  success: false;
  message: string;
  error: ApiErrorPayload;
}

/** A page of results, with the envelope's `meta` kept alongside the rows. */
export interface Page<T> {
  items: T[];
  meta: PageMeta;
}

/** Page controls every listing endpoint accepts, except storefront search. */
export interface PageParams {
  page?: number;
  page_size?: number;
}

/** Error codes the backend raises. Anything else is treated as unexpected. */
export type ApiErrorCode =
  | 'VALIDATION_ERROR'
  | 'NOT_FOUND'
  | 'CONFLICT'
  | 'AUTHENTICATION_FAILED'
  | 'PERMISSION_DENIED'
  | 'RATE_LIMITED'
  | 'SERVICE_UNAVAILABLE'
  | 'INTERNAL_ERROR'
  | 'UNKNOWN_STOREFRONT'
  | 'DEV_ONLY_ENDPOINT'
  | 'HTTP_ERROR';
