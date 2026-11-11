"""Bulk product upload from an Excel (.xlsx) or CSV file.

One row per variant. Rows with the same product_name + category form one
product; product-level columns are read from that product's first row. The
whole file is validated first and nothing is created unless every row is
valid, so a half-imported catalogue can't happen through bad data. New SKUs
only -- existing SKUs are reported, never overwritten.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from uuid import UUID
from zipfile import BadZipFile

from openpyxl import Workbook, load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalogue.models import Category, ProductVariant
from app.catalogue.schemas import (
    ProductCreate,
    ProductImageCreate,
    VariantCreate,
    VariantOptionValue,
)
from app.catalogue.service import ProductService, VariantService
from app.core.exceptions import ValidationError

MAX_IMPORT_ROWS = 2000
MAX_IMPORT_BYTES = 2 * 1024 * 1024

COLUMNS = [
    "product_name",
    "category",
    "sku",
    "variant_name",
    "price",
    "stock",
    "size",
    "colour",
    "sale_price",
    "low_stock_threshold",
    "status",
    "brand",
    "short_description",
    "description",
    "fabric",
    "occasion",
    "sleeve",
    "neckline",
    "fabric_details",
    "washing_instructions",
    "country_of_origin",
    "hsn_code",
    "gst_rate",
    "image_url",
]
REQUIRED = ["product_name", "category", "sku", "price", "image_url"]


def template_csv() -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(COLUMNS)
    return buffer.getvalue()


@dataclass
class ImportResult:
    rows: int = 0
    products: int = 0
    variants: int = 0
    errors: list[dict] = field(default_factory=list)
    dry_run: bool = True


def _first_error(exc: PydanticValidationError) -> str:
    err = exc.errors()[0]
    where = ".".join(str(p) for p in err.get("loc", ()))
    return f"{where}: {err.get('msg')}" if where else str(err.get("msg"))


def _blank(value: str | None) -> str | None:
    return value.strip() if value and value.strip() else None


def read_csv(data: bytes) -> tuple[list[str], list[dict[str, str]]]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValidationError("Save the sheet as CSV UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text))
    headers = [h.strip().lower() for h in reader.fieldnames or []]
    rows = [{(k or "").strip().lower(): (v or "") for k, v in r.items()} for r in reader]
    return headers, rows


def _xlsx_text(value) -> str:
    """Excel cell -> the text a CSV cell would hold (5.0 -> "5", empty -> "")."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def read_xlsx(data: bytes) -> tuple[list[str], list[dict[str, str]]]:
    """The first sheet of an .xlsx file: row 1 is the header, blank rows are skipped."""
    try:
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except (InvalidFileException, BadZipFile, KeyError, ValueError) as exc:
        raise ValidationError("This is not a valid .xlsx file") from exc
    try:
        sheet = workbook.worksheets[0]
        values = sheet.iter_rows(values_only=True)
        header_row = next(values, None) or ()
        headers = [_xlsx_text(h).lower() for h in header_row]
        rows = []
        for raw in values:
            if raw is None or all(v is None or str(v).strip() == "" for v in raw):
                continue
            if len(rows) >= MAX_IMPORT_ROWS:
                rows.append({})  # enough to trip the row limit below
                break
            rows.append(
                {
                    h: _xlsx_text(raw[i] if i < len(raw) else None)
                    for i, h in enumerate(headers)
                    if h
                }
            )
    finally:
        workbook.close()
    return headers, rows


def template_xlsx() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Products"
    sheet.append(COLUMNS)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


class ProductImporter:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id

    async def _category_ids(self) -> dict[str, UUID]:
        rows = (
            await self.session.execute(
                select(Category.id, Category.name).where(Category.tenant_id == self.tenant_id)
            )
        ).all()
        lookup: dict[str, UUID] = {}
        for category_id, name in rows:
            lookup[str(category_id)] = category_id
            lookup.setdefault(name.strip().lower(), category_id)
        return lookup

    async def run(self, data: bytes, *, dry_run: bool, file_format: str = "csv") -> ImportResult:
        if len(data) > MAX_IMPORT_BYTES:
            raise ValidationError("The file is larger than 2MB")
        headers, rows = read_xlsx(data) if file_format == "xlsx" else read_csv(data)
        missing = [c for c in REQUIRED if c not in headers]
        if missing:
            raise ValidationError("Missing columns: " + ", ".join(missing))

        if not rows:
            raise ValidationError("The file has no rows")
        if len(rows) > MAX_IMPORT_ROWS:
            raise ValidationError(f"At most {MAX_IMPORT_ROWS} rows per file")

        result = ImportResult(rows=len(rows), dry_run=dry_run)
        categories = await self._category_ids()
        seen_skus: set[str] = set()
        products: dict[tuple[str, UUID], dict] = {}

        for line, row in enumerate(rows, start=2):  # row 1 is the header
            def fail(message: str, line: int = line) -> None:
                result.errors.append({"row": line, "message": message})

            category_id = categories.get((row.get("category") or "").strip().lower()) or (
                categories.get((row.get("category") or "").strip())
            )
            if category_id is None:
                fail(f"Unknown category '{row.get('category')}'")
                continue

            sku = (row.get("sku") or "").strip().upper()
            if sku in seen_skus:
                fail(f"SKU {sku} appears twice in the file")
                continue
            seen_skus.add(sku)

            options = []
            if _blank(row.get("size")):
                options.append(VariantOptionValue(name="Size", value=row["size"].strip()))
            if _blank(row.get("colour")):
                options.append(VariantOptionValue(name="Color", value=row["colour"].strip()))
            try:
                variant = VariantCreate(
                    sku=sku,
                    name=_blank(row.get("variant_name"))
                    or " / ".join(o.value for o in options)
                    or "Standard",
                    price=row.get("price", "").strip(),
                    sale_price=_blank(row.get("sale_price")),
                    status=(_blank(row.get("status")) or "DRAFT").upper(),
                    options=options,
                    initial_quantity=int(_blank(row.get("stock")) or 0),
                    low_stock_threshold=int(_blank(row.get("low_stock_threshold")) or 0),
                )
            except (PydanticValidationError, ValueError) as exc:
                fail(
                    _first_error(exc)
                    if isinstance(exc, PydanticValidationError)
                    else "stock must be a whole number"
                )
                continue

            key = (row["product_name"].strip().lower(), category_id)
            if key not in products:
                try:
                    product = ProductCreate(
                        category_id=category_id,
                        name=row["product_name"].strip(),
                        status=(_blank(row.get("status")) or "DRAFT").upper(),
                        brand=_blank(row.get("brand")),
                        short_description=_blank(row.get("short_description")),
                        description=_blank(row.get("description")),
                        fabric=_blank(row.get("fabric")),
                        occasion=_blank(row.get("occasion")),
                        sleeve=_blank(row.get("sleeve")),
                        neckline=_blank(row.get("neckline")),
                        fabric_details=_blank(row.get("fabric_details")),
                        washing_instructions=_blank(row.get("washing_instructions")),
                        country_of_origin=_blank(row.get("country_of_origin")),
                        hsn_code=_blank(row.get("hsn_code")),
                        gst_rate=_blank(row.get("gst_rate")),
                        images=[ProductImageCreate(url=(row.get("image_url") or "").strip())],
                    )
                except PydanticValidationError as exc:
                    fail(_first_error(exc))
                    continue
                products[key] = {"product": product, "variants": []}
            products[key]["variants"].append(variant)

        existing = set(
            (
                await self.session.scalars(
                    select(func.upper(ProductVariant.sku)).where(
                        ProductVariant.tenant_id == self.tenant_id,
                        func.upper(ProductVariant.sku).in_(seen_skus),
                    )
                )
            ).all()
        )
        for line, row in enumerate(rows, start=2):
            if (row.get("sku") or "").strip().upper() in existing:
                result.errors.append(
                    {"row": line, "message": f"SKU {row['sku'].strip().upper()} already exists"}
                )

        result.products = len(products)
        result.variants = sum(len(p["variants"]) for p in products.values())
        if result.errors or dry_run:
            result.errors.sort(key=lambda e: e["row"])
            return result

        product_service = ProductService(self.session, self.tenant_id)
        variant_service = VariantService(self.session, self.tenant_id)
        for entry in products.values():
            created = await product_service.create(entry["product"])
            for variant in entry["variants"]:
                await variant_service.create(created.id, variant)
        return result
