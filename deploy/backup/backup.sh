#!/bin/sh
# Dump the CliQ. database (custom format, compressed) and prune old dumps.
#
#   backup.sh          one dump now
#   backup.sh --loop   one dump every BACKUP_INTERVAL_SECONDS, forever
#
# Uses the standard PG* environment variables. A dump is written to a
# temporary name and only renamed once pg_dump succeeded and the archive
# lists cleanly, so a half-written file is never mistaken for a backup.
set -eu

BACKUP_DIR=${BACKUP_DIR:-/backups}
KEEP_DAYS=${BACKUP_KEEP_DAYS:-14}
INTERVAL=${BACKUP_INTERVAL_SECONDS:-86400}

dump() {
    mkdir -p "$BACKUP_DIR"
    stamp=$(date -u +%Y%m%dT%H%M%SZ)
    final="$BACKUP_DIR/cliq-$stamp.dump"
    tmp="$final.partial"
    if pg_dump --format=custom --compress=6 --no-owner --file="$tmp" \
        && pg_restore --list "$tmp" >/dev/null; then
        mv "$tmp" "$final"
        echo "{\"logger\":\"backup\",\"status\":\"ok\",\"file\":\"$final\",\"bytes\":$(wc -c <"$final")}"
    else
        rm -f "$tmp"
        echo "{\"logger\":\"backup\",\"status\":\"failed\"}" >&2
        return 1
    fi
    find "$BACKUP_DIR" -name 'cliq-*.dump' -mtime +"$KEEP_DAYS" -print -delete | sed 's/^/pruned /'
}

if [ "${1:-}" = "--loop" ]; then
    while true; do
        dump || true
        sleep "$INTERVAL"
    done
else
    dump
fi
