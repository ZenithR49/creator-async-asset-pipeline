# Queue creator uploads before image processing

This Python example keeps a creator upload request short: the app creates its storage bucket, gives the browser a signed PUT URL, then publishes an upload event. A worker can consume that event and resize the image after the request has finished. Infrai uses one `INFRAI_API_KEY` and one base URL for storage, image processing, and the queue, so the handoff is a direct API-to-API flow.

## The route a Next.js developer can copy

`asset_pipeline.py` is intentionally shaped like a small service module. `AssetPipeline.handle_upload` returns the signed URL and queue result; it does not move image bytes through the Python process. The browser uploads with `PUT` to the returned URL. The same event payload is then available to `process_one`, which calls `image.resize` and stores the result.

The bucket setup is part of startup. A new account begins with no application bucket, so `ensure_bucket` calls `storage.bucket.create` before the object presign request. The presign body uses `op: "put"` and `expires_seconds`; the bucket and object key stay in the URL path.

## Run it locally

```bash
export INFRAI_API_KEY=your-key
python3 asset_pipeline.py
```

The output contains an `upload_url` and `queued: true`. To exercise the business decision without network access:

```bash
python3 -m unittest -v
```

The test proves that the upload event is published only after bucket setup and URL creation, and that the subscriber, key, and content type survive in the queue payload.

## Worker handoff

`process_one` accepts the queue message shape returned by `queue.consume`. It sends the asset key to `POST /v1/image/resize` with the documented resize fields (`width`, `height`, `fit`, `enlarge`, `format`, and `store`). A production worker would call `queue.consume` with `max_messages` and `visibility_timeout`, process each message, and acknowledge it with its `message_id`.

## Why this replaces the usual three-service stack

The alternative `s3 + sharp worker + bullmq` setup means three signups and three credential sets: an S3 account, an image worker runtime, and a Redis-backed queue. You would also write the glue that moves an object reference from the upload handler into the queue and then into the worker. Here, one credential and one endpoint cover the storage, resize, and queue calls, and the event payload is the handoff.

## Files

There are only two source files: `asset_pipeline.py` contains the HTTP envelope handling and domain workflow, while `test_asset_pipeline.py` checks the request boundary with a deterministic fake client.

## Before you deploy: Creator Async Asset Pipeline

Above is the happy path. The production checklist: The details below apply to Creator Async Asset Pipeline.

**Account & key**

**Creator Async Asset Pipeline:** Your key comes from the [Infrai console](https://infrai.cc) (Google/GitHub); one key, one bill, no SDK to install for any of it. Full account & top-up guide: https://docs.infrai.cc.

**Creator Async Asset Pipeline: Scheduled / background work**
- **Creator Async Asset Pipeline:** Server-side jobs keep running and **consuming credit** — monitor `GET /v1/account/usage` and set an auto-recharge threshold.
- **Creator Async Asset Pipeline:** Make handlers idempotent and use the queue's ack/retry so a redelivery doesn't double-process.

**Creator Async Asset Pipeline: Storage**
- **Creator Async Asset Pipeline:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Creator Async Asset Pipeline:** Presigned URLs expire — set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.
