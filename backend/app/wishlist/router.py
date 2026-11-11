from uuid import UUID

from fastapi import APIRouter, Depends, status  # type: ignore
from sqlalchemy.ext.asyncio import AsyncSession  # type: ignore

from app.auth.dependencies import require_customer
from app.core.database import get_db
from app.core.responses import ApiResponse, ok
from app.users.models import User  # type: ignore
from app.wishlist.schemas import WishListItemCreate, WishListRead
from app.wishlist.service import WishListService  # type: ignore

router = APIRouter(prefix="/wishlist", tags=["Wishlist"])


def _service(session: AsyncSession, user: User) -> WishListService:
    return WishListService(session, user.tenant_id, user.id)


@router.get("", response_model=ApiResponse[WishListRead], summary="get the current wishlist")
async def get_wishlist(
    session: AsyncSession = Depends(get_db), user: User = Depends(require_customer)
) -> ApiResponse[WishListRead]:
    wishlist = await _service(session, user).view()
    return ok(wishlist, message="wishlist retrieved successfully")


@router.post(
    "/items",
    response_model=ApiResponse[WishListRead],
    status_code=status.HTTP_201_CREATED,
    summary="add an item to the wishlist",
)
async def add_item(
    data: WishListItemCreate,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_customer),
) -> ApiResponse[WishListRead]:
    wishlist = await _service(session, user).add_item(data)
    return ok(wishlist, message="item added to wishlist successfully")


@router.delete(
    "/items/{item_id}",
    response_model=ApiResponse[WishListRead],
    summary="remove an item from the wishlist",
)
async def remove_item(
    item_id: UUID, session: AsyncSession = Depends(get_db), user: User = Depends(require_customer)
) -> ApiResponse[WishListRead]:
    wishlist = await _service(session, user).remove_item(item_id)
    return ok(wishlist, message="item removed from wishlist successfully")


@router.delete("", response_model=ApiResponse[WishListRead], summary="clear the wishlist")
async def clear_wishlist(
    session: AsyncSession = Depends(get_db), user: User = Depends(require_customer)
) -> ApiResponse[WishListRead]:
    wishlist = await _service(session, user).clear()
    return ok(wishlist, message="wishlist cleared successfully")
