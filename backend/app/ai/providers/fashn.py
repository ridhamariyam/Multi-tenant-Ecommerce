"""FASHN AI try-on (https://docs.fashn.ai, contract read 2026-11-07).

POST /v1/run {"model_name": "tryon-max", "inputs": {...}} -> {"id", "error"}
GET  /v1/status/{id} -> {"id", "status", "output": [...], "error": {"name", "message"}}
Statuses: starting, in_queue, processing, completed, failed. Outputs are CDN
URLs kept for three days, so the worker copies them into our own bucket.
Header x-fashn-credits-used reports the provider cost. There is no cancel
endpoint and no documented webhook signature.
"""

from __future__ import annotations

import base64
import binascii
from urllib.parse import quote, urlsplit

import httpx

from app.ai.providers.base import FetchedOutput, ProviderError, ProviderStatus, TryOnRequest

# Where FASHN serves outputs. Anything else is refused: the worker must not
# be steerable into fetching arbitrary URLs.
OUTPUT_HOSTS = frozenset({"cdn.fashn.ai", "media.fashn.ai"})
RETRYABLE_HTTP = {429, 500, 502, 503, 504}
RETRYABLE_RUNTIME = {"ThirdPartyError", "UnavailableError", "PipelineError"}

# tryon-v1.6 names its inputs differently from tryon-max.
_V16 = "tryon-v1.6"


def _data_uri(data: bytes, content_type: str) -> str:
    return f"data:{content_type};base64,{base64.b64encode(data).decode()}"


def decode_data_uri(value: str, *, max_bytes: int) -> FetchedOutput:
    header, _, payload = value.partition(",")
    if not header.startswith("data:") or ";base64" not in header:
        raise ProviderError("BadOutput", "Unsupported output encoding", retryable=False)
    if len(payload) > (max_bytes * 4) // 3 + 8:
        raise ProviderError("OutputTooLarge", "Generated image is too large", retryable=False)
    try:
        data = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ProviderError("BadOutput", "Output is not valid base64", retryable=False) from exc
    return FetchedOutput(data=data, content_type=header[5:].split(";")[0] or None)


class FashnProvider:
    name = "fashn"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model_name: str,
        timeout: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.model_name = model_name
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
            transport=transport,
        )
        self._download = httpx.AsyncClient(timeout=timeout, transport=transport, follow_redirects=False)

    def _inputs(self, request: TryOnRequest) -> dict:
        model = _data_uri(request.model_image, request.model_image_type)
        product = _data_uri(request.product_image, request.product_image_type)
        if self.model_name == _V16:
            mode = {"fast": "performance"}.get(request.generation_mode, request.generation_mode)
            inputs = {
                "model_image": model,
                "garment_image": product,
                "mode": mode,
                "num_samples": request.num_images,
                "output_format": request.output_format,
            }
        else:
            inputs = {
                "model_image": model,
                "product_image": product,
                "resolution": request.resolution,
                "generation_mode": request.generation_mode,
                "num_images": request.num_images,
                "output_format": request.output_format,
            }
            if request.prompt:
                inputs["prompt"] = request.prompt
        if request.seed is not None:
            inputs["seed"] = request.seed
        return inputs

    @staticmethod
    def _api_error(response: httpx.Response) -> ProviderError:
        try:
            body = response.json()
        except ValueError:
            body = {}
        code = str(body.get("error") or f"HTTP{response.status_code}")
        message = str(body.get("message") or "The AI provider refused the request")
        # OutOfCredits is a 429 but retrying will not help.
        retryable = response.status_code in RETRYABLE_HTTP and code != "OutOfCredits"
        return ProviderError(code, message, retryable=retryable)

    async def generate_tryon(self, request: TryOnRequest) -> str:
        params = {"webhook_url": request.webhook_url} if request.webhook_url else None
        try:
            response = await self._client.post(
                "/v1/run",
                params=params,
                json={"model_name": self.model_name, "inputs": self._inputs(request)},
            )
        except httpx.HTTPError as exc:
            raise ProviderError("NetworkError", "Could not reach the AI provider", retryable=True) from exc
        if response.status_code >= 400:
            raise self._api_error(response)
        body = response.json()
        if body.get("error") or not body.get("id"):
            raise ProviderError(
                str(body.get("error") or "NoPredictionId"),
                "The AI provider did not accept the request",
                retryable=False,
            )
        return str(body["id"])

    async def get_status(self, prediction_id: str) -> ProviderStatus:
        try:
            response = await self._client.get(f"/v1/status/{quote(prediction_id, safe='')}")
        except httpx.HTTPError as exc:
            raise ProviderError("NetworkError", "Could not reach the AI provider", retryable=True) from exc
        if response.status_code >= 400:
            raise self._api_error(response)
        body = response.json()
        credits = response.headers.get("x-fashn-credits-used")
        status = body.get("status")
        if status == "completed":
            outputs = [o for o in (body.get("output") or []) if isinstance(o, str)]
            return ProviderStatus(
                state="completed", outputs=outputs, credits_used=int(credits) if credits and credits.isdigit() else None,
                raw={"id": body.get("id"), "status": status},
            )  # fmt: skip
        if status in {"failed", "canceled", "cancelled"}:
            error = body.get("error") or {}
            name = str(error.get("name") or "ProviderFailed")
            return ProviderStatus(
                state="failed", error_code=name,
                error_message=str(error.get("message") or "The AI provider could not generate this image"),
                retryable=name in RETRYABLE_RUNTIME, raw={"id": body.get("id"), "status": status},
            )  # fmt: skip
        state = "processing" if status == "processing" else "starting"
        return ProviderStatus(state=state, raw={"id": body.get("id"), "status": status})

    async def handle_result(self, output: str, *, max_bytes: int) -> FetchedOutput:
        if output.startswith("data:"):
            return decode_data_uri(output, max_bytes=max_bytes)
        parts = urlsplit(output)
        if parts.scheme != "https" or (parts.hostname or "") not in OUTPUT_HOSTS:
            raise ProviderError("UntrustedOutput", "Output URL is not on the provider's CDN", retryable=False)
        try:
            async with self._download.stream("GET", output) as response:
                if response.status_code != 200:
                    raise ProviderError(
                        "OutputUnavailable", "Could not download the generated image",
                        retryable=response.status_code in RETRYABLE_HTTP,
                    )  # fmt: skip
                chunks, size = [], 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > max_bytes:
                        raise ProviderError("OutputTooLarge", "Generated image is too large", retryable=False)
                    chunks.append(chunk)
                return FetchedOutput(data=b"".join(chunks), content_type=response.headers.get("content-type"))
        except httpx.HTTPError as exc:
            raise ProviderError("NetworkError", "Could not download the generated image", retryable=True) from exc
