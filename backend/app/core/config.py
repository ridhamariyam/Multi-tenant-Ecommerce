from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.tenants.constants import DEFAULT_CURRENCY

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent

DEV_PLACEHOLDER_SECRETS = frozenset(
    {
        "dev-secret-change-later",
        "dev-refresh-secret-change-later",
        "replace-me-with-a-long-random-access-secret",
        "replace-me-with-a-different-long-random-refresh-secret",
        "change-me",
    }
)

KNOWN_ENVIRONMENTS = frozenset(
    {"development", "test", "testing", "staging", "production", "prod"}
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(REPO_ROOT / ".env"), str(BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "TWS E-Commerce API"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"

    database_url: str
    test_database_url: str | None = None
    redis_url: str

    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_recycle_seconds: int = 1800
    db_pool_timeout_seconds: int = 10
    db_statement_timeout_seconds: int = 15

    jwt_secret: str
    jwt_refresh_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14
    refresh_reuse_grace_seconds: int = 30

    # Platform (multi-brand SaaS). Every store is reachable at
    # <subdomain>.<platform_root_domain>; "localhost" works in development
    # because browsers resolve *.localhost to the loopback address.
    platform_root_domain: str = "localhost"
    # How a store's public address is shown to merchants. {subdomain} and
    # {root} are filled in; production would be "https://{subdomain}.{root}".
    storefront_url_template: str = "http://{subdomain}.{root}:3000"
    # Merchant accounts sign in once for the whole platform, then exchange
    # that session for a short-lived token bound to one brand.
    merchant_access_token_expire_minutes: int = 30
    merchant_refresh_token_expire_days: int = 14
    brand_token_expire_minutes: int = 30
    brand_registration_rate_limit_attempts: int = 5
    brand_registration_rate_limit_window_seconds: int = 3600

    phone_default_country_code: str = "91"
    phone_national_number_length: int = 10

    # MSG91 owns the OTP itself -- generation, delivery, expiry, retries and
    # attempt limits all sit with the widget. The account auth key is only
    # used to confirm, server-side, that a widget token really is verified;
    # it is never sent to the browser. See app/auth/widget.py.
    msg91_auth_key: str | None = None
    msg91_widget_verify_url: str = "https://control.msg91.com/api/v5/widget/verifyAccessToken"
    msg91_timeout_seconds: float = 10.0

    google_client_id: str | None = None

    # Google Sheets order export. One platform service account; each brand
    # shares its own spreadsheet with that account's email. The JSON key may
    # be given inline (raw or base64) or as a path to the key file.
    google_sheets_service_account_json: str | None = Field(default=None, repr=False)
    google_sheets_service_account_file: str | None = None
    google_sheets_api_url: str = "https://sheets.googleapis.com/v4"
    google_sheets_timeout_seconds: float = Field(default=15.0, gt=0, le=120)
    order_sheet_batch_size: int = Field(default=200, ge=1, le=1000)

    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    docs_enabled: bool | None = None

    trust_forwarded_host: bool = False

    login_rate_limit_attempts: int = 10
    login_ip_rate_limit_attempts: int = 30
    login_rate_limit_window_seconds: int = 60

    otp_request_rate_limit_attempts: int = 5
    otp_verify_rate_limit_attempts: int = 10
    otp_ip_rate_limit_attempts: int = 30
    refresh_rate_limit_attempts: int = 30
    otp_rate_limit_window_seconds: int = 300

    checkout_rate_limit_attempts: int = 20
    coupon_apply_rate_limit_attempts: int = 15
    review_rate_limit_attempts: int = 10
    search_rate_limit_attempts: int = 120
    guest_cart_rate_limit_attempts: int = 30
    guest_checkout_rate_limit_attempts: int = 10
    order_tracking_rate_limit_attempts: int = 20
    commerce_rate_limit_window_seconds: int = 60

    review_request_delay_days: int = 2
    cart_retention_days: int = 30
    store_utc_offset_minutes: int = 330

    # These credentials are only exposed as integration status; no external
    # email or alternate payment API is called by this integration.
    ccavenue_merchant_id: str | None = None
    ccavenue_access_code: str | None = None
    ccavenue_working_key: str | None = None

    # Shiprocket API user (Settings > API > Add New API User in the panel).
    # Server-side only; see app/shipments/shiprocket.py. Booking also needs a
    # tenant to enable it under Admin > Shipping provider.
    shiprocket_email: str | None = None
    shiprocket_password: str | None = None
    # Bind the deployment's API account to one tenant; other tenants cannot
    # use it or inspect its pickup locations. Use the map for separate accounts.
    shiprocket_tenant_id: str | None = None
    shiprocket_tenant_credentials: dict[UUID, dict[str, str]] = Field(
        default_factory=dict, repr=False
    )
    shiprocket_api_url: str = "https://apiv2.shiprocket.in/v1/external"
    shiprocket_timeout_seconds: float = Field(default=20.0, gt=0, le=120)
    # Shiprocket documents tokens as valid for 10 days; refresh well before.
    shiprocket_token_ttl_seconds: int = Field(default=9 * 24 * 3600, gt=0, lt=10 * 24 * 3600)
    # Retries for reads (tracking, rates) on 429/5xx/timeouts. Calls that book
    # or change something are never retried blindly.
    shiprocket_read_retries: int = Field(default=2, ge=0, le=5)
    # The token entered as the webhook "security token" in the panel; sent
    # back by Shiprocket as the x-api-key header. Unset = webhooks refused.
    shiprocket_webhook_token: str | None = None
    # How often a parcel in transit is re-checked when no webhook arrives.
    shipment_sync_interval_minutes: int = 60

    msg91_admin_otp_template_id: str | None = None
    email_provider_api_key: str | None = None
    whatsapp_provider_api_key: str | None = None

    storage_local_path: str = "var/uploads"
    storage_public_base_url: str = "/media"
    max_upload_bytes: int = 5 * 1024 * 1024
    # "local" keeps files on the API's disk (served at /media); "s3" uses a
    # bucket (MinIO in development) and enables presigned browser uploads.
    storage_backend: Literal["local", "s3"] = "local"
    s3_bucket: str = "cliq-media"
    s3_region: str = "us-east-1"
    s3_access_key_id: str | None = Field(default=None, repr=False)
    s3_secret_access_key: str | None = Field(default=None, repr=False)
    # How the API reaches the store (e.g. http://minio:9000 inside Docker).
    # Unset = AWS S3 itself.
    s3_endpoint_url: str | None = None
    # The same store as a browser sees it, used to sign upload URLs
    # (e.g. http://localhost:59000). Unset = s3_endpoint_url.
    s3_presign_endpoint_url: str | None = None
    # Where validated files are served from (a CDN in production). Unset =
    # <presign endpoint>/<bucket>.
    s3_public_base_url: str | None = None
    s3_presign_expire_seconds: int = Field(default=600, ge=60, le=3600)
    s3_pending_retention_days: int = Field(default=1, ge=1, le=30)
    # Create the bucket, policy and lifecycle rule at startup (development).
    s3_create_bucket: bool = False
    image_max_dimension: int = 2000

    # --- AI generation (Phases 8-10) ---------------------------------------
    # "fashn" = FASHN API (needs FASHN_API_KEY); "mock" = a local stand-in that
    # composes a labelled preview image, for development and tests only (refused
    # in production); unset = AI Studio reports that no provider is configured.
    ai_provider: Literal["fashn", "mock"] | None = None
    fashn_api_key: str | None = Field(default=None, repr=False)
    fashn_api_url: str = "https://api.fashn.ai"
    fashn_model_name: str = "tryon-max"
    # FASHN documents no webhook signature. Our webhook URL carries this
    # secret, and the payload is never trusted: it only triggers a status
    # check against the FASHN API. Unset = no webhook, polling only.
    fashn_webhook_secret: str | None = Field(default=None, repr=False)
    # Public base URL of this API, used to build the webhook callback URL.
    public_api_url: str | None = None
    fashn_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    # FASHN's default account concurrency is 6 in-flight predictions.
    ai_provider_concurrency: int = Field(default=6, ge=1, le=100)
    ai_max_active_jobs_per_brand: int = Field(default=10, ge=1, le=1000)
    ai_job_timeout_seconds: int = Field(default=900, ge=60, le=7200)
    ai_poll_interval_seconds: int = Field(default=4, ge=1, le=60)
    ai_max_submit_attempts: int = Field(default=3, ge=1, le=10)
    # Celery broker/result backend; default = REDIS_URL.
    celery_broker_url: str | None = None
    # Run tasks inline instead of through the broker (tests).
    celery_task_always_eager: bool = False

    seed_tenant_name: str = "CliQ."
    seed_tenant_slug: str = "zeen"
    seed_tenant_currency: str = DEFAULT_CURRENCY
    seed_tenant_domain: str = "localhost"
    seed_admin_phone: str | None = None
    seed_admin_email: str | None = None
    seed_admin_password: str | None = None

    razorpay_key_id: str | None = None
    razorpay_key_secret: str | None = None
    razorpay_webhook_secret: str | None = None
    razorpay_api_url: str = "https://api.razorpay.com/v1"
    razorpay_timeout_seconds: float = 10.0
    # The pair .env keeps per gateway environment; RAZORPAY_ENVIRONMENT picks
    # one. An explicit RAZORPAY_KEY_ID / _KEY_SECRET still wins over both.
    razorpay_environment: str = "sandbox"
    sandbox_razorpay_api_key: str | None = None
    sandbox_razorpay_api_secret: str | None = None
    production_razorpay_api_key: str | None = None
    production_razorpay_api_secret: str | None = None

    online_payment_expiry_minutes: int = 30

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                return value
            return [origin.strip() for origin in stripped.split(",") if origin.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def api_docs_enabled(self) -> bool:
        if self.docs_enabled is None:
            return not self.is_production
        return self.docs_enabled

    @model_validator(mode="after")
    def _select_razorpay_credentials(self) -> Settings:
        live = self.razorpay_environment.strip().lower() == "production"
        key, secret = (
            (self.production_razorpay_api_key, self.production_razorpay_api_secret)
            if live
            else (self.sandbox_razorpay_api_key, self.sandbox_razorpay_api_secret)
        )
        # .env.example ships "your_..." placeholders; those are not credentials.
        if secret and secret.startswith("your_"):
            key, secret = None, None
        self.razorpay_key_id = self.razorpay_key_id or key
        self.razorpay_key_secret = self.razorpay_key_secret or secret
        return self

    @model_validator(mode="after")
    def _validate_production_safety(self) -> Settings:
        if self.environment.lower() not in KNOWN_ENVIRONMENTS:
            raise ValueError(
                f"Unknown ENVIRONMENT {self.environment!r}; expected one of "
                + ", ".join(sorted(KNOWN_ENVIRONMENTS))
            )
        if self.is_production:
            placeholders = [
                name
                for name, value in (
                    ("JWT_SECRET", self.jwt_secret),
                    ("JWT_REFRESH_SECRET", self.jwt_refresh_secret),
                )
                if value in DEV_PLACEHOLDER_SECRETS or len(value) < 32
            ]
            if placeholders:
                raise ValueError(
                    "Refusing to start in production with weak/placeholder secrets: "
                    + ", ".join(placeholders)
                )
            if "*" in self.cors_origins:
                raise ValueError("Refusing to start in production with CORS_ORIGINS='*'")
        if self.is_production and self.ai_provider == "mock":
            raise ValueError("AI_PROVIDER=mock is for development only")
        if self.storage_backend == "s3" and not self.s3_bucket.strip():
            raise ValueError("STORAGE_BACKEND=s3 needs S3_BUCKET")
        if self.jwt_secret == self.jwt_refresh_secret:
            raise ValueError("JWT_SECRET and JWT_REFRESH_SECRET must differ")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
