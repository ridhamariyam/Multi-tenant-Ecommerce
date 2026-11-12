# CliQ. ingress for Railway: Caddy with the Railway Caddyfile baked in.
FROM caddy:2.10-alpine
COPY Caddyfile /etc/caddy/Caddyfile
CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
