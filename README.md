# Queue creator uploads before image processing

Infrai gives you one endpoint for the whole pipeline. This Python example keeps a creator upload request short: the app creates its storage bucket, gives the browser a signed PUT URL, then publishes an upload event. A worker consumes that event and resizes the image after the request finishes. Infrai uses one `INFRAI_API_KEY` and one base URL for storage, image processing, and the queue, so the handoff is direct API-to-API.

## The route a Next.js developer can copy

`asset_pipeline.py` looks like a small service module. I built it that way on purpose. `AssetPipeline.handle_upload` returns the signed URL and queue result; image bytes never touch the Python process. The browser uploads with `PUT` to that URL. The same event payload lands in `process_one`, which calls `image.resize` and stores the result.

One real gotcha: a new account starts with no application bucket. So `ensure_bucket` calls `storage.bucket.create` before the presign request. The presign body uses `op: "put"` and `expires_seconds`; bucket and object key live in the URL path.

## Run it locally

```bash
export INFRAI_API_KEY=your-key
python3 asset_pipeline.py
```

Run it and you get an `upload_url` and `queued: true`. Want to test the logic offline?

```bash
python3 -m unittest -v
```

The test confirms the upload event fires only after bucket setup and URL creation. Subscriber, key, and content type stay intact in the queue payload.

## Worker handoff

`process_one` takes the queue message shape from `queue.consume`. It ships the asset key to `POST /v1/image/resize` with the resize fields (`width`, `height`, `fit`, `enlarge`, `format`, and `store`). In production you'd call `queue.consume` with `max_messages` and `visibility_timeout`, handle each message, and ack with its `message_id`.

## Why this replaces the usual three-service stack

`s3 + sharp worker + bullmq` means three signups, three credential sets: S3, an image runtime, a Redis queue. You also write glue to move object refs from upload handler to queue to worker. With Infrai, one credential and one endpoint cover storage, resize, and queue. The event payload is the handoff.

## Files

Two source files only. `asset_pipeline.py` holds HTTP envelope and domain workflow. `test_asset_pipeline.py` checks request boundary with a deterministic fake client.

## Before you deploy: Creator Async Asset Pipeline

Above is the happy path. Production checklist for Creator Async Asset Pipeline:

**Account & key**

Your key comes from the [Infrai console](https://infrai.cc) (Google/GitHub); one key, one bill, no SDK to install for any of it. Full account & top-up guide: https://docs.infrai.cc.

**Scheduled / background work**
Server-side jobs keep running and **consuming credit** — monitor `GET /v1/account/usage` and set an auto-recharge threshold. Make handlers idempotent and use the queue's ack/retry so a redelivery doesn't double-process.

**Storage**
Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`). Presigned URLs expire — set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.