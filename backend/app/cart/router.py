from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.constants import UserRole
from app.auth.dependencies import CurrentUserOptional, require_customer
from app.cart.schemas import CartItemCreate, CartItemUpdate, CartRead
from app.cart.service import CartService
from app.core import rate_limit
from app.core.config import get_settings
from app.core.database import get_db
from app.core.error_codes import AuthErrorCode
from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.core.request_context import client_ip
from app.core.responses import ApiResponse, ok
from app.tenants.resolver import CurrentTenant
from app.users.models import User

router = APIRouter(prefix="/cart", tags=["Cart"])

CART_TOKEN_HEADER = "X-Cart-Token"
MAX_CART_TOKEN_LENGTH = 128


@dataclass
class CartOwner:
    """Who the cart belongs to: a signed-in customer, or a guest's cart token."""

    tenant_id: UUID
    customer_id: UUID | None
    guest_token: str | None


async def cart_owner(
    tenant: CurrentTenant,
    user: CurrentUserOptional,
    cart_token: str | None = Header(
        default=None,
        alias=CART_TOKEN_HEADER,
        max_length=MAX_CART_TOKEN_LENGTH,
        description="Guest cart token from POST /cart/guest (ignored when signed in)",
    ),
) -> CartOwner:
    if user is not None:
        if user.role != UserRole.CUSTOMER.value:
            raise PermissionDeniedError("Insufficient permissions")
        return CartOwner(tenant_id=user.tenant_id, customer_id=user.id, guest_token=None)

    if cart_token:
        return CartOwner(tenant_id=tenant.id, customer_id=None, guest_token=cart_token)

    raise AuthenticationError("Not authenticated", error_code=AuthErrorCode.NOT_AUTHENTICATED)


def _service(session: AsyncSession, owner: CartOwner) -> CartService:
    return CartService(
        session, owner.tenant_id, owner.customer_id, guest_token=owner.guest_token
    )


@router.post(
    "/guest",
    response_model=ApiResponse[CartRead],
    status_code=status.HTTP_201_CREATED,
    summary="Start a guest cart (no account needed)",
)
async def create_guest_cart(
    request: Request,
    tenant: CurrentTenant,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[CartRead]:
    settings = get_settings()
    await rate_limit.enforce(
        "guest-cart",
        str(tenant.id),
        client_ip(request),
        limit=settings.guest_cart_rate_limit_attempts,
        window_seconds=settings.commerce_rate_limit_window_seconds,
    )
    cart = await CartService(session, tenant.id).create_guest_cart()
    return ok(cart, message="Guest cart created")


@router.post(
    "/merge",
    response_model=ApiResponse[CartRead],
    summary="Move a guest cart into the signed-in customer's cart",
)
async def merge_guest_cart(
    cart_token: str = Header(alias=CART_TOKEN_HEADER, max_length=MAX_CART_TOKEN_LENGTH),
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_customer),
) -> ApiResponse[CartRead]:
    cart = await CartService(session, user.tenant_id, user.id).merge_guest_cart(cart_token)
    return ok(cart, message="Guest cart merged")


@router.get("", response_model=ApiResponse[CartRead], summary="Get the current cart")
async def get_cart(
    session: AsyncSession = Depends(get_db),
    owner: CartOwner = Depends(cart_owner),
) -> ApiResponse[CartRead]:
    cart = await _service(session, owner).view()
    return ok(cart, message="Cart retrieved")


@router.post(
    "/items",
    response_model=ApiResponse[CartRead],
    status_code=status.HTTP_201_CREATED,
    summary="Add a variant to the cart",
)
async def add_item(
    data: CartItemCreate,
    session: AsyncSession = Depends(get_db),
    owner: CartOwner = Depends(cart_owner),
) -> ApiResponse[CartRead]:
    cart = await _service(session, owner).add_item(data)
    return ok(cart, message="Item added to cart")


@router.patch(
    "/items/{item_id}",
    response_model=ApiResponse[CartRead],
    summary="Update a cart item's quantity",
)
async def update_item(
    item_id: UUID,
    data: CartItemUpdate,
    session: AsyncSession = Depends(get_db),
    owner: CartOwner = Depends(cart_owner),
) -> ApiResponse[CartRead]:
    cart = await _service(session, owner).update_item(item_id, data)
    return ok(cart, message="Cart item updated")


@router.delete(
    "/items/{item_id}",
    response_model=ApiResponse[CartRead],
    summary="Remove a cart item",
)
async def remove_item(
    item_id: UUID,
    session: AsyncSession = Depends(get_db),
    owner: CartOwner = Depends(cart_owner),
) -> ApiResponse[CartRead]:
    cart = await _service(session, owner).remove_item(item_id)
    return ok(cart, message="Cart item removed")


@router.delete("", response_model=ApiResponse[CartRead], summary="Clear the cart")
async def clear_cart(
    session: AsyncSession = Depends(get_db),
    owner: CartOwner = Depends(cart_owner),
) -> ApiResponse[CartRead]:
    cart = await _service(session, owner).clear()
    return ok(cart, message="Cart cleared")
