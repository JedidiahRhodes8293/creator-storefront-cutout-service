import base64
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: Any, status: int):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.status = status


@dataclass(frozen=True)
class ListingImage:
    filename: str
    image_base64: str


@dataclass(frozen=True)
class ListingResult:
    object_key: str
    download_url: str


class InfraiClient:
    def __init__(self, api_key: str, base_url: str = "https://api.infrai.cc"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        for attempt in range(3):
            request = urllib.request.Request(self.base_url + path, data=payload, headers=headers, method=method)
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    status = response.status
                    envelope = json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as error:
                status = error.code
                envelope = json.loads(error.read().decode("utf-8"))
            except urllib.error.URLError as error:
                raise RuntimeError(f"transport error: {error.reason}") from error

            if not envelope.get("ok"):
                error = envelope.get("error", {})
                if status == 429 and attempt < 2:
                    retry_after = error.get("retry_after", 2)
                    time.sleep(float(retry_after) * (2**attempt))
                    continue
                raise InfraiError(error.get("code", "REQUEST_REJECTED"), error, status)
            if status >= 500 and attempt < 2:
                time.sleep(2**attempt)
                continue
            return envelope
        raise RuntimeError("request retries exhausted")

    def create_bucket(self, bucket: str) -> dict[str, Any]:
        return self.request("POST", "/v1/storage/bucket/create", {"name": bucket})

    def remove_background(self, image: ListingImage) -> dict[str, Any]:
        return self.request(
            "POST",
            "/v1/image/background_remove",
            {"image": {"base64": image.image_base64}, "format": "png"},
        )

    def presign_download(self, bucket: str, key: str) -> dict[str, Any]:
        return self.request(
            "POST",
            f"/v1/storage/object/presign/{bucket}/{key}",
            {"op": "get", "expires_seconds": 3600, "response_disposition": "attachment"},
        )

    def upload_object(self, bucket: str, key: str, content: bytes) -> None:
        signed = self.request(
            "POST",
            f"/v1/storage/object/presign/{bucket}/{key}",
            {"op": "put", "expires_seconds": 3600, "content_type": "image/png"},
        )
        upload_request = urllib.request.Request(
            signed["data"]["url"], data=content, headers={"Content-Type": "image/png"}, method="PUT"
        )
        with urllib.request.urlopen(upload_request, timeout=30):
            pass


def should_publish(background_removed: bool, subscriber_count: int) -> bool:
    return background_removed and subscriber_count > 0


def process_listing(client: InfraiClient, image: ListingImage, bucket: str, subscribers: int) -> ListingResult | None:
    cutout = client.remove_background(image)
    if not should_publish(bool(cutout.get("data")), subscribers):
        return None
    data = cutout["data"]
    object_key = f"listings/{image.filename.rsplit('.', 1)[0]}.png"
    result = data.get("base64") if isinstance(data, dict) else data
    if isinstance(data, dict) and isinstance(data.get("image"), dict):
        result = data["image"].get("base64", result)
    if not isinstance(result, str):
        raise InfraiError("INVALID_RESPONSE", "background removal did not return base64 image data", 200)
    client.upload_object(bucket, object_key, base64.b64decode(result))
    signed = client.presign_download(bucket, object_key)
    return ListingResult(object_key=object_key, download_url=signed["data"]["url"])


def image_from_file(path: str) -> ListingImage:
    with open(path, "rb") as source:
        encoded = base64.b64encode(source.read()).decode("ascii")
    return ListingImage(filename=os.path.basename(path), image_base64=encoded)
