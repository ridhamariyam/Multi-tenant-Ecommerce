# CliQ. admin / merchant console — production image (Next.js standalone server).
# NEXT_PUBLIC_* values and the /api/v1 proxy target are compiled in: build args.

FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:20-alpine AS build
WORKDIR /app
ARG NEXT_PUBLIC_API_ORIGIN=http://api:8000
ARG NEXT_PUBLIC_STOREFRONT_URL=
ARG NEXT_PUBLIC_PLATFORM_ROOT_DOMAIN
ARG NEXT_PUBLIC_AUTH_IDLE_TIMEOUT_MINUTES=30
ENV NEXT_TELEMETRY_DISABLED=1 \
    NEXT_PUBLIC_API_ORIGIN=$NEXT_PUBLIC_API_ORIGIN \
    NEXT_PUBLIC_STOREFRONT_URL=$NEXT_PUBLIC_STOREFRONT_URL \
    NEXT_PUBLIC_PLATFORM_ROOT_DOMAIN=$NEXT_PUBLIC_PLATFORM_ROOT_DOMAIN \
    NEXT_PUBLIC_AUTH_IDLE_TIMEOUT_MINUTES=$NEXT_PUBLIC_AUTH_IDLE_TIMEOUT_MINUTES
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN test -n "$NEXT_PUBLIC_PLATFORM_ROOT_DOMAIN" || (echo "NEXT_PUBLIC_PLATFORM_ROOT_DOMAIN build arg is required" >&2; exit 1)
RUN npm run build

FROM node:20-alpine AS run
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3001 HOSTNAME=0.0.0.0
RUN addgroup -S app -g 1001 && adduser -S app -u 1001 -G app
COPY --from=build --chown=app:app /app/.next/standalone ./
COPY --from=build --chown=app:app /app/.next/static ./.next/static
USER app
EXPOSE 3001
HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
  CMD wget -qO- http://127.0.0.1:3001/admin/signin >/dev/null || exit 1
CMD ["node", "server.js"]
