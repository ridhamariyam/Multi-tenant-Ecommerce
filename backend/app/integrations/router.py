"""Which external services are connected, for the admin settings screen.

Nothing here talks to a provider. It reports, per service, whether its
credentials are present in the environment and what the backend does with
it today, so pending work is visible instead of faked.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth.dependencies import require_permission
from app.auth.permissions import Permission
from app.core.config import get_settings
from app.core.responses import ApiResponse, ok
from app.integrations.schemas import IntegrationStatus
from app.shipments import shiprocket
from app.users.models import User

router = APIRouter(prefix="/admin/integrations", tags=["Admin-Integrations"])




def _entry(
    key, name, purpose, settings_names, integrated, note, *, configured=None
) -> IntegrationStatus:
    settings = get_settings()
    if configured is None:
        configured = all(getattr(settings, field, None) for field in settings_names)
    if integrated and configured:
        status = "ACTIVE"
    elif configured:
        status = "CREDENTIALS_PRESENT_INTEGRATION_PENDING"
    else:
        status = "PENDING_CREDENTIALS"
    return IntegrationStatus(
        key=key,
        name=name,
        purpose=purpose,
        credentials_configured=configured,
        integrated=integrated,
        status=status,
        required_settings=[f.upper() for f in settings_names],
        note=note,
    )


@router.get(
    "",
    response_model=ApiResponse[list[IntegrationStatus]],
    summary="Connection status of external services",
)
async def list_integrations(
    user: User = Depends(require_permission(Permission.SETTINGS_VIEW, legacy_staff=True)),
) -> ApiResponse[list[IntegrationStatus]]:
    return ok(
        [
            _entry(
                "razorpay",
                "Razorpay",
                "Online checkout and payment verification",
                ["razorpay_key_id", "razorpay_key_secret"],
                False,
                "Checkout and verification code is present; production enablement must wait "
                "for migration review and isolated validation. Credential presence alone "
                "does not certify the database schema.",
            ),
            _entry(
                "ccavenue",
                "CCAvenue",
                "Online payments (UPI, cards, net banking, wallets) and refunds",
                ["ccavenue_merchant_id", "ccavenue_access_code", "ccavenue_working_key"],
                False,
                "CCAvenue is not integrated. COD advances are confirmed by staff "
                "until a supported gateway is added.",
            ),
            _entry(
                "shiprocket",
                "Shiprocket",
                "Courier booking, AWB labels, live tracking, serviceability",
                ["shiprocket_email", "shiprocket_password", "shiprocket_tenant_id"],
                True,
                "Booking, AWB, labels, pickups, manifests, cancellation and tracking "
                "(webhook + periodic sync). Each store enables it under Settings > Shipping "
                "provider. Webhooks need SHIPROCKET_WEBHOOK_TOKEN. Checkout still charges "
                "the configured delivery rate, not a live courier quote.",
                configured=shiprocket.is_configured(user.tenant_id),
            ),
            _entry(
                "msg91_customer_otp",
                "MSG91 OTP widget",
                "Customer sign-in by OTP",
                ["msg91_auth_key"],
                True,
                "Verifies widget tokens server-side.",
            ),
            _entry(
                "msg91_admin_otp",
                "MSG91 admin OTP",
                "Two-factor sign-in for admin and staff",
                ["msg91_auth_key", "msg91_admin_otp_template_id"],
                False,
                "Admin login is password-only until an OTP template is provided.",
            ),
            _entry(
                "email",
                "Email provider",
                "Order, shipping and review-request emails",
                ["email_provider_api_key"],
                False,
                "Review requests are logged, not sent, until a provider is connected.",
            ),
            _entry(
                "whatsapp",
                "WhatsApp Business API",
                "Order updates and customer messages on WhatsApp",
                ["whatsapp_provider_api_key"],
                False,
                "Not connected.",
            ),
        ],
        message="Integrations",
    )
