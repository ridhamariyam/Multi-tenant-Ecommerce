"""CliQ. nightly backup for Railway (run as a cron service; exits when done).

1. pg_dump the database (custom format) and check the archive reads back.
2. Upload it to the backup bucket (separate storage from the database and
   MinIO volumes) as db/<UTC timestamp>.dump with its SHA-256.
3. Copy product images that are not in the backup yet (keys are immutable)
   from MinIO to media/<key>; pending/ uploads are skipped.
4. Delete database dumps older than BACKUP_KEEP_DAYS (always keeps 3).
5. Restore drill: download the dump just uploaded, check its SHA-256,
   restore it into a throwaway database on the same server, compare row
   counts with the live database, drop it.

Prints one JSON line per step and a summary; exits 1 on any failure (Railway
shows the run as failed) and posts to ALERT_WEBHOOK_URL when that is set.
Never prints credentials.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

import boto3
from botocore.config import Config

DUMP = "/tmp/cliq.dump"
COUNTED = ("tenants", "products", "orders", "users", "brand_subscriptions")


def log(step: str, **fields) -> None:
    print(json.dumps({"job": "backup", "step": step, **fields}), flush=True)


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if not value:
        raise SystemExit(f"{name} is not set")
    return value


def s3(prefix: str):
    style = os.environ.get(f"{prefix}_URL_STYLE", "path")
    return boto3.client(
        "s3",
        endpoint_url=env(f"{prefix}_ENDPOINT"),
        region_name=os.environ.get(f"{prefix}_REGION", "us-east-1"),
        aws_access_key_id=env(f"{prefix}_ACCESS_KEY_ID"),
        aws_secret_access_key=env(f"{prefix}_SECRET_ACCESS_KEY"),
        config=Config(s3={"addressing_style": "virtual" if style.startswith("virtual") else "path"}, retries={"max_attempts": 5}),
    )


def psql(sql: str, database: str | None = None) -> str:
    args = ["psql", "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-c", sql]
    if database:
        args += ["-d", database]
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()


def counts(database: str | None = None) -> dict[str, int]:
    return {t: int(psql(f"SELECT count(*) FROM {t}", database)) for t in COUNTED}


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def alert(text: str) -> None:
    url = os.environ.get("ALERT_WEBHOOK_URL")
    if not url:
        return
    body = json.dumps({"text": text, "content": text}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(url, body, {"Content-Type": "application/json"}), timeout=10)
    except Exception:  # alerting must not hide the real failure
        pass


def main() -> None:
    started = time.time()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = s3("BACKUP_S3")
    bucket = env("BACKUP_S3_BUCKET")
    database = env("PGDATABASE")

    # 1. dump + archive check
    live = counts()
    revision = psql("SELECT version_num FROM alembic_version")
    subprocess.run(["pg_dump", "-Fc", "--no-owner", "-f", DUMP], check=True)
    toc = subprocess.run(["pg_restore", "--list", DUMP], check=True, capture_output=True, text=True).stdout
    digest = sha256(DUMP)
    size = os.path.getsize(DUMP)
    log("dump", bytes=size, toc_entries=toc.count("\n"), revision=revision, counts=live)

    # 2. upload
    key = f"db/cliq-{stamp}.dump"
    backup.upload_file(DUMP, bucket, key, ExtraArgs={"Metadata": {"sha256": digest, "revision": revision}})
    head = backup.head_object(Bucket=bucket, Key=key)
    if head["ContentLength"] != size:
        raise RuntimeError("uploaded dump size differs from local dump")
    log("upload", key=key, sha256=digest)

    # 3. media mirror
    copied = 0
    if os.environ.get("MEDIA_S3_ENDPOINT"):
        media = s3("MEDIA_S3")
        media_bucket = env("MEDIA_S3_BUCKET")
        have: set[str] = set()
        for page in backup.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix="media/"):
            have.update(o["Key"][len("media/"):] for o in page.get("Contents", []))
        for page in media.get_paginator("list_objects_v2").paginate(Bucket=media_bucket):
            for obj in page.get("Contents", []):
                k = obj["Key"]
                if k.startswith("pending/") or k in have:
                    continue
                body = media.get_object(Bucket=media_bucket, Key=k)
                backup.put_object(Bucket=bucket, Key=f"media/{k}", Body=body["Body"].read(),
                                  ContentType=body.get("ContentType", "application/octet-stream"))
                copied += 1
        log("media", copied=copied, already_backed_up=len(have))

    # 4. retention
    keep_days = int(os.environ.get("BACKUP_KEEP_DAYS", "14"))
    dumps = []
    for page in backup.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix="db/"):
        dumps += page.get("Contents", [])
    dumps.sort(key=lambda o: o["LastModified"])
    cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
    expired = [o["Key"] for o in dumps[:-3] if o["LastModified"] < cutoff]
    for k in expired:
        backup.delete_object(Bucket=bucket, Key=k)
    log("retention", kept=len(dumps) - len(expired), deleted=len(expired))

    # 5. restore drill from the uploaded copy
    if os.environ.get("RESTORE_DRILL", "1") == "1":
        os.remove(DUMP)
        backup.download_file(bucket, key, DUMP)
        if sha256(DUMP) != digest:
            raise RuntimeError("downloaded dump does not match the uploaded checksum")
        drill = f"cliq_restore_drill_{stamp.lower()}"
        psql(f'CREATE DATABASE "{drill}"', "postgres")
        try:
            subprocess.run(["pg_restore", "--no-owner", "--exit-on-error", "-d", drill, DUMP], check=True)
            restored = counts(drill)
            restored_rev = psql("SELECT version_num FROM alembic_version", drill)
            if restored != live or restored_rev != revision:
                raise RuntimeError(f"restore drill mismatch: live={live} restored={restored}")
            log("restore_drill", database=drill, counts=restored, revision=restored_rev, result="ok")
        finally:
            psql(f'DROP DATABASE IF EXISTS "{drill}"', "postgres")
    log("done", seconds=round(time.time() - started, 1), database=database)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        log("failed", error=f"{type(exc).__name__}: {str(exc)[:300]}")
        alert(f"CliQ. backup FAILED: {type(exc).__name__}: {str(exc)[:200]}")
        sys.exit(1)
