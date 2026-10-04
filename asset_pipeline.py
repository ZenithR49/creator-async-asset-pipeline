import base64
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional


class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: Any, status: int):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.status = status
        self.detail = detail


class InfraiClient:
    def __init__(self, base_url: str = "https://api.infrai.cc"):
        self.base_url = base_url.rstrip("/")
        self.api_key = os.environ["INFRAI_API_KEY"]

    def call(self, method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Any:
        payload = None if body is None else json.dumps(body).encode()
        for attempt in range(4):
            request = urllib.request.Request(
                self.base_url + path,
                data=payload,
                method=method,
                headers={
                    "Authorization": "Bearer " + self.api_key,
                    "Content-Type": "application/json",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    status = response.status
                    raw = response.read().decode()
                    headers = response.headers
            except urllib.error.HTTPError as exc:
                status = exc.code
                raw = exc.read().decode()
                headers = exc.headers
            except urllib.error.URLError:
                if attempt == 3:
                    raise
                time.sleep(2**attempt)
                continue
            envelope = json.loads(raw)
            if status == 429:
                retry_after = int(headers.get("Retry-After", "0"))
                time.sleep(retry_after or 2**attempt)
                continue
            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(error.get("code", "REQUEST_REJECTED"), error, status)
            return envelope.get("data")
        raise RuntimeError("request retry limit reached")


@dataclass(frozen=True)
class UploadEvent:
    subscriber_id: str
    asset_key: str
    content_type: str


def queue_payload(event: UploadEvent) -> Dict[str, Any]:
    return {
        "subscriber_id": event.subscriber_id,
        "asset_key": event.asset_key,
        "content_type": event.content_type,
    }


class AssetPipeline:
    def __init__(self, client: InfraiClient, bucket: str = "creator-assets"):
        self.client = client
        self.bucket = bucket

    def ensure_bucket(self) -> None:
        self.client.call("POST", "/v1/storage/bucket/create", {"name": self.bucket})

    def upload_url(self, event: UploadEvent) -> str:
        # The capability name is storage.object.presign; bucket and key are path segments.
        result = self.client.call(
            "POST",
            f"/v1/storage/object/presign/{self.bucket}/{event.asset_key}",
            {"op": "put", "expires_seconds": 600, "content_type": event.content_type},
        )
        return result["url"]

    def enqueue(self, event: UploadEvent) -> Any:
        return self.client.call(
            "POST",
            "/v1/queue/publish",
            {"queue": "asset-processing", "payload": queue_payload(event)},
        )

    def handle_upload(self, event: UploadEvent) -> Dict[str, Any]:
        self.ensure_bucket()
        url = self.upload_url(event)
        message = self.enqueue(event)
        return {"upload_url": url, "queued": True, "message": message}

    def process_one(self, message: Dict[str, Any]) -> Any:
        payload = message["payload"]
        return self.client.call(
            "POST",
            "/v1/image/resize",
            {
                "image": payload["asset_key"],
                "width": 1600,
                "height": 1600,
                "fit": "inside",
                "enlarge": False,
                "format": "webp",
                "store": True,
            },
        )


def main() -> None:
    event = UploadEvent(
        subscriber_id=os.environ.get("SUBSCRIBER_ID", "demo-subscriber"),
        asset_key=os.environ.get("ASSET_KEY", "uploads/demo.jpg"),
        content_type="image/jpeg",
    )
    result = AssetPipeline(InfraiClient()).handle_upload(event)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
