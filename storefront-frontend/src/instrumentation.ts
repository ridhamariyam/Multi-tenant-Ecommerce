import type { Instrumentation } from "next";

export function register() {}

/**
 * Server-side render/route errors as one JSON line each, so they reach the same
 * log collector as the API's (and can be alerted on with `"level":"error"`).
 * Only the path is logged: query strings can carry tokens.
 */
export const onRequestError: Instrumentation.onRequestError = async (error, request, context) => {
  const err = error as Error & { digest?: string };
  console.error(
    JSON.stringify({
      ts: new Date().toISOString(),
      level: "error",
      logger: "next",
      msg: err.message,
      digest: err.digest,
      method: request.method,
      path: request.path.split("?")[0],
      route: context.routePath,
      route_type: context.routeType,
      request_id: (request.headers["x-request-id"] as string | undefined) ?? undefined,
      stack: err.stack?.split("\n").slice(0, 8).join("\n"),
    }),
  );
};
