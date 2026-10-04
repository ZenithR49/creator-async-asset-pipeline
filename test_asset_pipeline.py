from asset_pipeline import AssetPipeline, UploadEvent, queue_payload


class FakeClient:
    def __init__(self):
        self.calls = []

    def call(self, method, path, body=None):
        self.calls.append((method, path, body))
        if path.startswith("/v1/storage/object/presign/"):
            return {"url": "https://uploads.example/signed"}
        if path == "/v1/queue/publish":
            return {"message_id": "m-1"}
        return {"ok": True}


def test_upload_is_handed_to_queue_after_signed_url():
    client = FakeClient()
    event = UploadEvent("sub-7", "uploads/hero.jpg", "image/jpeg")
    result = AssetPipeline(client).handle_upload(event)

    assert result["queued"] is True
    assert client.calls[0][1] == "/v1/storage/bucket/create"
    assert client.calls[2][1] == "/v1/queue/publish"
    assert client.calls[2][2]["payload"] == queue_payload(event)
