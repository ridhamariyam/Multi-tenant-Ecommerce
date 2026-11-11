#!/bin/sh
# Serve the storefront at https://tws.test:3000.
#
# Phone sign-in cannot run on plain http://localhost: MSG91's hCaptcha rejects
# localhost, and its encryption needs Web Crypto, which browsers only expose
# over HTTPS. Requires "127.0.0.1 tws.test" in /etc/hosts. The certificate is
# self-signed, so the browser warns once.
set -eu
DIR=certificates
if [ ! -f "$DIR/tws.test.pem" ]; then
    mkdir -p "$DIR"
    openssl req -x509 -newkey rsa:2048 -nodes -days 825 -subj /CN=tws.test \
        -addext subjectAltName=DNS:tws.test \
        -keyout "$DIR/tws.test-key.pem" -out "$DIR/tws.test.pem" 2>/dev/null
fi
exec npx next dev --turbopack --hostname tws.test --port 3000 \
    --experimental-https \
    --experimental-https-key "$DIR/tws.test-key.pem" \
    --experimental-https-cert "$DIR/tws.test.pem"
