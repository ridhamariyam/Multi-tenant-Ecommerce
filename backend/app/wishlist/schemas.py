from uuid import UUID

from pydantic import BaseModel

from app.catalogue.schemas import ProductImageSummary


class WishListItemCreate(BaseModel):
    variant_id: UUID


class WishListItemRead(BaseModel):
    id: UUID
    variant_id: UUID
    product_id: UUID
    product_name: str
    variant_name: str
    sku: str
    unit_price: float
    image: ProductImageSummary | None = None


class WishListRead(BaseModel):
    id: UUID
    items: list[WishListItemRead] = []
    item_count: int = 0
