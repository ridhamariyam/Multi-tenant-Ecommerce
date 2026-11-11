"""Which external services are connected, for the admin settings screen.

Nothing here talks to a provider. It reports, per service, whether its
credentials are present in the environment and what the backend does with
it today, so pending work is visible instead of faked.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_permission
from app.auth.permissions import Permission
from app.core.config import get_settings
from app.core.database import get_db
from app.core.responses import ApiResponse, ok
from app.integrations import google_sheets
from app.integrations.models import OrderSheetSettings
from app.integrations.order_sheets import OrderSheetService
from app.integrations.schemas import (
    IntegrationStatus,
    OrderSheetSettingsRead,
    OrderSheetSettingsUpdate,
    OrderSheetSyncRead,
)
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
                "google_sheets",
                "Google Sheets",
                "Every successful order written to the store's own spreadsheet",
                ["google_sheets_service_account_json"],
                True,
                "Orders are appended by the order-sheets worker within a minute of becoming "
                "a sale (COD when placed, online once paid). Each store connects its sheet "
                "below. Server key: GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON (or _FILE).",
                configured=google_sheets.is_configured(),
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


async def _sheet_read(service: OrderSheetService, settings: OrderSheetSettings) -> OrderSheetSettingsRead:
    pending, exported = await service.counts(settings)
    return OrderSheetSettingsRead(
        credentials_configured=google_sheets.is_configured(),
        service_account_email=google_sheets.service_account_email(),
        is_enabled=settings.is_enabled,
        spreadsheet_id=settings.spreadsheet_id,
        spreadsheet_url=google_sheets.spreadsheet_url(settings.spreadsheet_id)
        if settings.spreadsheet_id
        else None,
        worksheet_name=settings.worksheet_name,
        last_synced_at=settings.last_synced_at,
        last_error=settings.last_error,
        last_error_at=settings.last_error_at,
        pending_orders=pending,
        exported_orders=exported,
    )


@router.get(
    "/google-sheets",
    response_model=ApiResponse[OrderSheetSettingsRead],
    summary="Google Sheets order export for this store",
)
async def get_order_sheet(
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.SETTINGS_VIEW, legacy_staff=True)),
) -> ApiResponse[OrderSheetSettingsRead]:
    service = OrderSheetService(session, user.tenant_id)
    settings = await service.get_settings()
    return ok(await _sheet_read(service, settings), message="Google Sheets export")


@router.put(
    "/google-sheets",
    response_model=ApiResponse[OrderSheetSettingsRead],
    summary="Connect a spreadsheet and turn the order export on or off",
)
async def update_order_sheet(
    data: OrderSheetSettingsUpdate,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.SETTINGS_MANAGE)),
) -> ApiResponse[OrderSheetSettingsRead]:
    service = OrderSheetService(session, user.tenant_id)
    settings = await service.update_settings(
        is_enabled=data.is_enabled,
        spreadsheet=data.spreadsheet,
        worksheet_name=data.worksheet_name,
        user_id=user.id,
    )
    return ok(await _sheet_read(service, settings), message="Google Sheets export saved")


@router.post(
    "/google-sheets/sync",
    response_model=ApiResponse[OrderSheetSyncRead],
    summary="Write orders waiting for the sheet now, instead of on the next worker run",
)
async def sync_order_sheet(
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.SETTINGS_MANAGE)),
) -> ApiResponse[OrderSheetSyncRead]:
    result = await OrderSheetService(session, user.tenant_id).sync()
    return ok(
        OrderSheetSyncRead(exported=result.exported, pending=result.pending, error=result.error),
        message="Orders written to the sheet" if not result.error else "Export failed",
    )
