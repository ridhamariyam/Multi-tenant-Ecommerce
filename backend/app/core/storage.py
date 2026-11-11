"""Where uploaded files live: local disk, or an S3 bucket (MinIO in development).

Two kinds of key exist:

* **Final keys** ``<tenant_id>/<hex>.<ext>``: validated files, publicly readable.
* **Pending keys** ``pending/<tenant_id>/<hex>``: where a browser puts a file with a
  presigned upload. Nothing reads them until the API has checked the bytes and copied
  them to a final key; the bucket policy keeps them private and a lifecycle rule
  removes any that are never completed.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

from app.core.config import Settings, get_settings

PENDING_PREFIX = "pending"
PRIVATE_PREFIX = "private"
_PENDING_KEY = re.compile(
    r"^pending/(?P<tenant>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/"
    r"(?P<token>[0-9a-f]{32})$"
)


class StorageError(Exception):
    """The storage backend failed or is unreachable."""


@dataclass(frozen=True)
class PresignedUpload:
    """What a browser needs to POST one file straight to the bucket."""

    url: str
    fields: dict[str, str]
    key: str
    expires_at: datetime


@dataclass(frozen=True)
class StoredObject:
    data: bytes
    content_type: str | None


class Storage(Protocol):
    """Somewhere to put bytes and get back a URL that serves them."""

    supports_presigned_uploads: bool

    async def save(self, data: bytes, *, key: str, content_type: str) -> str: ...

    async def delete(self, key: str) -> None: ...


class PresignedStorage(Storage, Protocol):
    async def presign_upload(
        self, *, key: str, content_type: str, max_bytes: int
    ) -> PresignedUpload: ...

    async def read(self, key: str, *, max_bytes: int) -> StoredObject | None:
        """The object's bytes, or None if it does not exist. Larger than max_bytes raises."""
        ...


class ObjectTooLargeError(StorageError):
    pass


class _MissingError(StorageError):
    """The key or bucket does not exist (handled inside S3Storage)."""


_MISSING = frozenset({"404", "NoSuchKey", "NotFound", "NoSuchBucket"})


class LocalStorage:
    """Writes under a directory the app also serves as static files."""

    supports_presigned_uploads = False

    def __init__(self, root: Path, public_base_url: str) -> None:
        self.root = root
        self.public_base_url = public_base_url.rstrip("/")

    async def save(self, data: bytes, *, key: str, content_type: str) -> str:
        target = self.root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return f"{self.public_base_url}/{key}"

    async def delete(self, key: str) -> None:
        target = self.root / key
        if target.is_file():
            target.unlink()

    def key_for_url(self, url: str) -> str | None:
        prefix = f"{self.public_base_url}/"
        if not url.startswith(prefix):
            return None
        key = url[len(prefix):]
        return key if _safe_key(key) else None

    async def read(self, key: str, *, max_bytes: int) -> StoredObject | None:
        if not _safe_key(key):
            return None
        target = self.root / key
        if not target.is_file():
            return None
        if target.stat().st_size > max_bytes:
            raise ObjectTooLargeError(key)
        return StoredObject(data=target.read_bytes(), content_type=None)

    def clear(self) -> None:
        """Drop everything. Tests use this; nothing in the app should."""
        if self.root.exists():
            shutil.rmtree(self.root)


class S3Storage:
    """An S3 bucket. boto3 is synchronous, so each call runs in a worker thread."""

    supports_presigned_uploads = True

    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        access_key_id: str | None,
        secret_access_key: str | None,
        endpoint_url: str | None,
        presign_endpoint_url: str | None,
        public_base_url: str | None,
        presign_expire_seconds: int,
        pending_retention_days: int = 1,
    ) -> None:
        import boto3
        from botocore.config import Config

        self.bucket = bucket
        self.presign_expire_seconds = presign_expire_seconds
        self.pending_retention_days = pending_retention_days
        # Path-style addressing works for MinIO and for AWS alike, and keeps
        # bucket names with dots valid under TLS.
        config = Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            retries={"max_attempts": 3, "mode": "standard"},
            connect_timeout=5,
            read_timeout=30,
        )
        common: dict[str, Any] = {
            "region_name": region,
            "aws_access_key_id": access_key_id,
            "aws_secret_access_key": secret_access_key,
            "config": config,
        }
        self._client = boto3.client("s3", endpoint_url=endpoint_url, **common)
        # The API reaches MinIO as http://minio:9000 inside Docker, but a browser
        # must be handed a URL it can resolve; the signature covers the host, so
        # presigned URLs are signed by a client that uses the public endpoint.
        self._presign_client = (
            boto3.client("s3", endpoint_url=presign_endpoint_url, **common)
            if presign_endpoint_url and presign_endpoint_url != endpoint_url
            else self._client
        )
        if public_base_url:
            self.public_base_url = public_base_url.rstrip("/")
        else:
            base = (presign_endpoint_url or endpoint_url or f"https://s3.{region}.amazonaws.com")
            self.public_base_url = f"{base.rstrip('/')}/{bucket}"

    async def _run(self, fn, /, **kwargs):
        """Call boto3 off the event loop; any failure becomes StorageError."""
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            return await asyncio.to_thread(fn, **kwargs)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in _MISSING:
                raise _MissingError(code) from exc
            raise StorageError(f"{fn.__name__}: {code}") from exc
        except BotoCoreError as exc:
            raise StorageError(str(exc)) from exc

    def url_for(self, key: str) -> str:
        return f"{self.public_base_url}/{key}"

    def key_for_url(self, url: str) -> str | None:
        prefix = f"{self.public_base_url}/"
        if not url.startswith(prefix):
            return None
        key = url[len(prefix):]
        return key if _safe_key(key) else None

    async def save(self, data: bytes, *, key: str, content_type: str) -> str:
        private = key.startswith(f"{PRIVATE_PREFIX}/")
        await self._run(
            self._client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            CacheControl="private, max-age=0" if private else "public, max-age=31536000, immutable",
        )
        return self.url_for(key)

    async def signed_url(self, key: str, *, expires_seconds: int = 900) -> str:
        """A time-limited GET link for a private object."""
        return await self._run(
            self._presign_client.generate_presigned_url,
            ClientMethod="get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_seconds,
        )

    async def delete(self, key: str) -> None:
        await self._run(self._client.delete_object, Bucket=self.bucket, Key=key)

    async def presign_upload(
        self, *, key: str, content_type: str, max_bytes: int
    ) -> PresignedUpload:
        """A POST policy: exactly this key, this content type, 1..max_bytes bytes."""
        post = await self._run(
            self._presign_client.generate_presigned_post,
            Bucket=self.bucket,
            Key=key,
            Fields={"Content-Type": content_type},
            Conditions=[
                {"Content-Type": content_type},
                ["content-length-range", 1, max_bytes],
            ],
            ExpiresIn=self.presign_expire_seconds,
        )
        return PresignedUpload(
            url=post["url"],
            fields=dict(post["fields"]),
            key=key,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=self.presign_expire_seconds),
        )

    async def read(self, key: str, *, max_bytes: int) -> StoredObject | None:
        try:
            head = await self._run(self._client.head_object, Bucket=self.bucket, Key=key)
            if head["ContentLength"] > max_bytes:
                raise ObjectTooLargeError(key)
            response = await self._run(
                self._client.get_object, Bucket=self.bucket, Key=key, Range=f"bytes=0-{max_bytes}"
            )
        except _MissingError:
            return None
        try:
            body = await asyncio.to_thread(response["Body"].read)
        except Exception as exc:
            raise StorageError(f"reading {key}") from exc
        if len(body) > max_bytes:
            raise ObjectTooLargeError(key)
        return StoredObject(data=body, content_type=response.get("ContentType"))

    def public_read_policy(self) -> dict[str, Any]:
        arn = f"arn:aws:s3:::{self.bucket}"
        return {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "PublicReadValidatedMedia",
                    "Effect": "Allow",
                    "Principal": {"AWS": ["*"]},
                    "Action": ["s3:GetObject"],
                    "Resource": [f"{arn}/*"],
                },
                {
                    "Sid": "PendingAndPrivateMediaAreNotPublic",
                    "Effect": "Deny",
                    "Principal": {"AWS": ["*"]},
                    "Action": ["s3:GetObject"],
                    "Resource": [f"{arn}/{PENDING_PREFIX}/*", f"{arn}/{PRIVATE_PREFIX}/*"],
                },
            ],
        }

    async def ensure_bucket(self) -> list[str]:
        """Create the bucket, its read policy and the pending-upload expiry. Idempotent."""
        done: list[str] = []
        try:
            await self._run(self._client.head_bucket, Bucket=self.bucket)
        except _MissingError:
            await self._run(self._client.create_bucket, Bucket=self.bucket)
            done.append(f"created bucket {self.bucket}")
        await self._run(
            self._client.put_bucket_policy,
            Bucket=self.bucket,
            Policy=json.dumps(self.public_read_policy()),
        )
        done.append("public read on validated media; pending/ and private/ not public")
        await self._run(
            self._client.put_bucket_lifecycle_configuration,
            Bucket=self.bucket,
            LifecycleConfiguration={
                "Rules": [
                    {
                        "ID": "expire-abandoned-uploads",
                        "Status": "Enabled",
                        "Filter": {"Prefix": f"{PENDING_PREFIX}/"},
                        "Expiration": {"Days": self.pending_retention_days},
                    }
                ]
            },
        )
        done.append(f"pending uploads expire after {self.pending_retention_days} day(s)")
        return done


def _safe_key(key: str) -> bool:
    return bool(key) and "?" not in key and "#" not in key and "\\" not in key and ".." not in key.split("/")


def upload_key(tenant_id: uuid.UUID, extension: str) -> str:
    """A server-chosen name, tenant-partitioned; nothing in it comes from the client."""
    return f"{tenant_id}/{uuid.uuid4().hex}{extension}"


def private_key(tenant_id: uuid.UUID, *parts: str) -> str:
    return "/".join((PRIVATE_PREFIX, str(tenant_id), *parts))


def pending_key(tenant_id: uuid.UUID) -> str:
    return f"{PENDING_PREFIX}/{tenant_id}/{uuid.uuid4().hex}"


def parse_pending_key(key: str) -> tuple[uuid.UUID, str] | None:
    """(tenant_id, token) for a well-formed pending key, else None."""
    match = _PENDING_KEY.match(key)
    if match is None:
        return None
    return uuid.UUID(match["tenant"]), match["token"]


def build_storage(settings: Settings) -> Storage:
    if settings.storage_backend == "s3":
        return S3Storage(
            bucket=settings.s3_bucket,
            region=settings.s3_region,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key,
            endpoint_url=settings.s3_endpoint_url,
            presign_endpoint_url=settings.s3_presign_endpoint_url,
            public_base_url=settings.s3_public_base_url,
            presign_expire_seconds=settings.s3_presign_expire_seconds,
            pending_retention_days=settings.s3_pending_retention_days,
        )
    return LocalStorage(Path(settings.storage_local_path), settings.storage_public_base_url)


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        _storage = build_storage(get_settings())
    return _storage


def set_storage(storage: Storage | None) -> None:
    """Replace the backend (tests), or reset it so the next call rebuilds from settings."""
    global _storage
    _storage = storage
