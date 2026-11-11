"""DEVELOPMENT ONLY: a stand-in provider that needs no API key.

It does not do virtual try-on. It composes the model photo and the product
photo side by side under a "MOCK PREVIEW" banner, so the whole pipeline
(queue, worker, storage, review, lookbooks) can be exercised end to end.
Refused when ENVIRONMENT=production. Every job records provider="mock".
"""

from __future__ import annotations

import base64
import io
import json
import uuid

from PIL import Image, ImageDraw

from app.ai.providers.base import FetchedOutput, ProviderStatus, TryOnRequest
from app.ai.providers.fashn import decode_data_uri
from app.core.cache import get_redis

# Kept in Redis because Celery submits and polls in different processes.
_KEY = "ai:mock-prediction:{}"
_TTL_SECONDS = 3600


def _compose(request: TryOnRequest, index: int) -> str:
    model = Image.open(io.BytesIO(request.model_image)).convert("RGB")
    product = Image.open(io.BytesIO(request.product_image)).convert("RGB")
    height = 640
    model = model.resize((max(1, model.width * height // model.height), height))
    product.thumbnail((height // 2, height // 2))
    canvas = Image.new("RGB", (model.width + product.width + 24, height + 40), (245, 245, 245))
    canvas.paste(model, (0, 40))
    canvas.paste(product, (model.width + 12, 40 + (height - product.height) // 2))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, canvas.width, 32), fill=(20, 20, 20))
    draw.text((10, 9), f"MOCK PREVIEW - not a real try-on (#{index + 1})", fill=(255, 255, 255))
    buffer = io.BytesIO()
    fmt = "JPEG" if request.output_format == "jpeg" else "PNG"
    canvas.save(buffer, format=fmt)
    mime = "image/jpeg" if fmt == "JPEG" else "image/png"
    return f"data:{mime};base64,{base64.b64encode(buffer.getvalue()).decode()}"


class MockProvider:
    name = "mock"
    model_name = "mock-preview"

    async def generate_tryon(self, request: TryOnRequest) -> str:
        prediction_id = f"mock-{uuid.uuid4().hex}"
        outputs = [_compose(request, i) for i in range(request.num_images)]
        await get_redis().set(_KEY.format(prediction_id), json.dumps(outputs), ex=_TTL_SECONDS)
        return prediction_id

    async def get_status(self, prediction_id: str) -> ProviderStatus:
        stored = await get_redis().get(_KEY.format(prediction_id))
        if stored is None:
            return ProviderStatus(
                state="failed", error_code="MockPredictionExpired",
                error_message="The mock prediction expired", retryable=False,
            )  # fmt: skip
        return ProviderStatus(
            state="completed", outputs=json.loads(stored), credits_used=0,
            raw={"id": prediction_id, "status": "completed", "mock": True},
        )  # fmt: skip

    async def handle_result(self, output: str, *, max_bytes: int) -> FetchedOutput:
        return decode_data_uri(output, max_bytes=max_bytes)
