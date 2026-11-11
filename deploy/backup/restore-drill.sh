#!/bin/sh
# Prove a backup can be restored: load it into a throwaway PostgreSQL and run
# sanity checks. Never touches the live database.
#
#   deploy/backup/restore-drill.sh path/to/cliq-YYYYmmddTHHMMSSZ.dump
#
# Exit 0 only if the restore finished and the checks passed.
set -eu

DUMP=${1:?usage: restore-drill.sh <dump file>}
[ -f "$DUMP" ] || { echo "no such file: $DUMP" >&2; exit 1; }
NAME=cliq-restore-drill-$$
PASSWORD=$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')

cleanup() { docker rm -f -v "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

docker run -d --name "$NAME" --network none -e POSTGRES_PASSWORD="$PASSWORD" \
    -e POSTGRES_DB=restore_drill --tmpfs /var/lib/postgresql/data postgres:16 >/dev/null
i=0
until docker exec "$NAME" pg_isready -U postgres -d restore_drill >/dev/null 2>&1; do
    i=$((i + 1)); [ $i -lt 60 ] || { echo "postgres did not start" >&2; exit 1; }; sleep 1
done
sleep 2

docker cp "$DUMP" "$NAME:/tmp/restore.dump"
docker exec "$NAME" pg_restore --no-owner --exit-on-error -U postgres -d restore_drill /tmp/restore.dump

q() { docker exec "$NAME" psql -U postgres -d restore_drill -Atc "$1"; }
echo "migration:  $(q 'select version_num from alembic_version')"
echo "brands:     $(q 'select count(*) from tenants')"
echo "products:   $(q 'select count(*) from products')"
echo "orders:     $(q 'select count(*) from orders')"
echo "customers:  $(q "select count(*) from users where role = 'CUSTOMER'")"
# Integrity: every order's total still satisfies the stored equation.
bad=$(q "select count(*) from orders where total_amount <> subtotal - discount_amount + shipping_amount + cod_fee + tax_amount - tax_included_amount")
[ "$bad" = "0" ] || { echo "orders with inconsistent totals: $bad" >&2; exit 1; }
[ "$(q 'select count(*) from tenants')" -gt 0 ] || { echo "no brands restored" >&2; exit 1; }
echo "restore drill passed: $DUMP"
