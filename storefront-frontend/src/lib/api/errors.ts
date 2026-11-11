import type { ApiErrorCode, ApiErrorDetail } from '@/types/api';

/**
 * A failed API call, normalised from the backend's error envelope.
 *
 * The backend answers every failure with `{success, message, error}`, so the
 * status code, machine-readable code and per-field validation details are
 * always available rather than having to be guessed from the body.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: ApiErrorCode | string;
  readonly details: ApiErrorDetail[];
  readonly requestId: string | null;
  readonly retryAfterSeconds: number | null;

  constructor(init: {
    status: number;
    code: string;
    message: string;
    details?: ApiErrorDetail[];
    requestId?: string | null;
    retryAfterSeconds?: number | null;
  }) {
    super(init.message);
    this.name = 'ApiError';
    this.status = init.status;
    this.code = init.code;
    this.details = init.details ?? [];
    this.requestId = init.requestId ?? null;
    this.retryAfterSeconds = init.retryAfterSeconds ?? null;
  }

  get isUnauthenticated(): boolean {
    return this.status === 401;
  }

  get isForbidden(): boolean {
    return this.status === 403;
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }

  get isRateLimited(): boolean {
    return this.status === 429;
  }

  /** Validation details keyed by field, ready to bind to form inputs. */
  fieldErrors(): Record<string, string> {
    const errors: Record<string, string> = {};

    for (const detail of this.details) {
      if (detail.field && !(detail.field in errors)) {
        errors[detail.field] = detail.message;
      }
    }

    return errors;
  }
}

/** A network or parsing failure, where the backend never answered. */
export class ApiUnreachableError extends Error {
  constructor(cause?: unknown) {
    super('Could not reach the CliQ API.');
    this.name = 'ApiUnreachableError';
    this.cause = cause;
  }
}
