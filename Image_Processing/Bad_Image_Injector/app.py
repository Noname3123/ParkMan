import os
import re
import sys
import json
import time
import uuid
import argparse
from datetime import datetime, timezone
from typing import Optional, Tuple, List

import boto3


# ============================================================
# Bad Image Injector
# ============================================================
# Usage:
#  - Injects "bad" images into S3 (MinIO) to simulate faulty inputs.
#
# Principle:
#  - You provide a "bad" image file (e.g. empty parking lot, corrupted image, etc.)
#  - The script uploads it to S3 with a generated key naming that mimics real images.
#
# CHANGE: You can customize:
#  - S3 endpoint, bucket, prefix
#  - Naming convention for injected images
#  - Timestamping mode (current time, floored to hour, custom)
# ============================================================


# =========================
# DEFAULT CONFIG (env)
# =========================

# CHANGE: S3/MinIO endpoint
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://minio:9000")  # CHANGE
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "minioadmin")      # CHANGE
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "minioadmin")      # CHANGE
S3_REGION = os.getenv("S3_REGION", "us-east-1")               # CHANGE

# CHANGE: Default bucket in which to inject images
DEFAULT_BUCKET = os.getenv("S3_BUCKET_NAME", "camera-images")  # CHANGE

# CHANGE: Default prefix (folder) under which to inject images
DEFAULT_PREFIX = os.getenv("S3_PREFIX", "")  # CHANGE

# CHANGE: Default local output dir for "local" mode
DEFAULT_LOCAL_OUT = os.getenv("LOCAL_OUT_DIR", "./_inject_out")  # CHANGE

# CHANGE: Default bad image path
DEFAULT_BAD_IMAGE_PATH = os.getenv("BAD_IMAGE_PATH", "./bad_samples/empty_parking.jpg")  # CHANGE


# =========================
# KEY NAMING / TIMESTAMP
# =========================

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def floor_to_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)

def build_s3_key(prefix: str, ts: datetime, ext: str, cam_id: Optional[str] = None) -> str:
    """
    Generates S3 key for injected image based on timestamp and other parameters.

    CHANGE: Here is an example naming convention:
    Structure:
      - folders: YYYY/MM/DD/HH/
      - filename: YYYYMMDD_HHMMSS_<camid>_<uuid>.jpg

    Time:
      - Image Fetcher can parse timestamp from this naming.
      - timestamp parsig is simple since we control the format here.
    """
    # CHANGE: folder structure
    folder = f"{ts.year:04d}/{ts.month:02d}/{ts.day:02d}/{ts.hour:02d}/"  # CHANGE

    # CHANGE: cam id (if there are multiple cameras)
    cam_part = f"{cam_id}_" if cam_id else ""  # CHANGE

    # CHANGE: filename format
    fname = f"{ts.year:04d}{ts.month:02d}{ts.day:02d}_{ts.hour:02d}{ts.minute:02d}{ts.second:02d}_{cam_part}{uuid.uuid4().hex[:8]}{ext}"  # CHANGE

    # prefix sanitization
    if prefix and not prefix.endswith("/"):
        prefix = prefix + "/"

    return f"{prefix}{folder}{fname}"


# =========================
# S3 CLIENT
# =========================

def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,             # CHANGE
        aws_access_key_id=S3_ACCESS_KEY,      # CHANGE
        aws_secret_access_key=S3_SECRET_KEY,  # CHANGE
        region_name=S3_REGION,                # CHANGE
    )

def ensure_bucket_exists(s3, bucket: str) -> None:
    """
    MiniIO creates buckets on first use, so this is optional.
    CHANGE: Remove this if you don't want auto-create.
    """
    try:
        s3.head_bucket(Bucket=bucket)
    except Exception:
        # Try create
        s3.create_bucket(Bucket=bucket)


# =========================
# IO HELPERS
# =========================

def read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()

def infer_ext(path: str) -> str:
    _, ext = os.path.splitext(path)
    if not ext:
        return ".jpg"  # CHANGE: default extension
    return ext

def write_local(out_dir: str, filename: str, data: bytes) -> str:
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, filename)
    with open(out_path, "wb") as f:
        f.write(data)
    return out_path


# =========================
# CORE INJECTION
# =========================

def inject_to_s3(
    bad_image_path: str,
    bucket: str,
    prefix: str,
    ts_mode: str,
    cam_id: Optional[str],
    custom_ts: Optional[str],
    count: int,
) -> None:
    """
    Injects count bad images into S3.

    ts_mode:
      - "now": use current UTC timestamp (can be any time)
      - "hour": use floor_to_hour(now) (simulates images taken at start of hour)
      - "custom": use custom_ts ISO string
    """
    s3 = get_s3_client()
    ensure_bucket_exists(s3, bucket)

    data = read_bytes(bad_image_path)
    ext = infer_ext(bad_image_path)

    for i in range(count):
        if ts_mode == "now":
            ts = utc_now()
        elif ts_mode == "hour":
            ts = floor_to_hour(utc_now())
        elif ts_mode == "custom":
            if not custom_ts:
                raise ValueError("custom_ts is required when ts_mode=custom")
            # CHANGE: we expect ISO format
            # fromisoformat does not support 'Z', so replace with +00:00
            s = custom_ts.replace("Z", "+00:00")
            ts = datetime.fromisoformat(s)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            else:
                ts = ts.astimezone(timezone.utc)
        else:
            raise ValueError(f"Unknown ts_mode: {ts_mode}")

        key = build_s3_key(prefix=prefix, ts=ts, ext=ext, cam_id=cam_id)

        # CHANGE: metadata is used to mark injected images
        metadata = {
            "injected": "true",                 # CHANGE
            "inject_reason": "bad_image_test",  # CHANGE
            "inject_ts_utc": utc_now().isoformat(),
        }

        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=data,
            ContentType="image/jpeg",  # CHANGE: if not jpg, adjust accordingly
            Metadata=metadata,
        )

        print(f"[BadInjector] Uploaded bad image to s3://{bucket}/{key}")

def inject_to_local(
    bad_image_path: str,
    out_dir: str,
    ts_mode: str,
    cam_id: Optional[str],
    custom_ts: Optional[str],
    count: int,
) -> None:
    """
    Injects count bad images into local directory and imitates naming like S3 key (without folder by prefix).
    """
    data = read_bytes(bad_image_path)
    ext = infer_ext(bad_image_path)

    for i in range(count):
        if ts_mode == "now":
            ts = utc_now()
        elif ts_mode == "hour":
            ts = floor_to_hour(utc_now())
        elif ts_mode == "custom":
            if not custom_ts:
                raise ValueError("custom_ts is required when ts_mode=custom")
            s = custom_ts.replace("Z", "+00:00")
            ts = datetime.fromisoformat(s)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            else:
                ts = ts.astimezone(timezone.utc)
        else:
            raise ValueError(f"Unknown ts_mode: {ts_mode}")

        # Reuse build_s3_key to get the same naming; just replace prefix
        fake_key = build_s3_key(prefix="", ts=ts, ext=ext, cam_id=cam_id)

        # Locally: create folders (or use filename-safe)
        # CHANGE: I choose to create folders like in S3
        local_rel = fake_key  # npr. 2025/12/26/18/20251226_180000_cam_XXXX.jpg
        local_path = os.path.join(out_dir, local_rel)
        os.makedirs(os.path.dirname(local_path), exist_ok=True)

        with open(local_path, "wb") as f:
            f.write(data)

        print(f"[BadInjector] Wrote bad image to {local_path}")


# =========================
# CLI
# =========================

def parse_args():
    p = argparse.ArgumentParser(description="Bad Image Injector (S3/Local)")

    # CHANGE: modes
    p.add_argument("--mode", choices=["s3", "local"], default="s3")  # CHANGE

    # input bad image
    p.add_argument("--bad-image", default=DEFAULT_BAD_IMAGE_PATH, help="Path to bad image file")  # CHANGE

    # common options
    p.add_argument("--count", type=int, default=1, help="How many images to inject")  # CHANGE
    p.add_argument("--ts-mode", choices=["now", "hour", "custom"], default="now", help="Timestamp mode")  # CHANGE
    p.add_argument("--custom-ts", default=None, help="Custom ISO timestamp, e.g. 2025-12-26T18:00:00Z")  # CHANGE
    p.add_argument("--cam-id", default=None, help="Optional camera id to embed in filename")  # CHANGE

    # s3 options
    p.add_argument("--bucket", default=DEFAULT_BUCKET, help="S3 bucket to inject into")  # CHANGE
    p.add_argument("--prefix", default=DEFAULT_PREFIX, help="S3 prefix (folder root)")  # CHANGE

    # local options
    p.add_argument("--out-dir", default=DEFAULT_LOCAL_OUT, help="Local output dir for injected images")  # CHANGE

    return p.parse_args()

def main():
    args = parse_args()

    if not os.path.exists(args.bad_image):
        print(f"[BadInjector] ERROR: bad image not found: {args.bad_image}")
        sys.exit(1)

    print("[BadInjector] Starting with config:")
    print(json.dumps({
        "mode": args.mode,
        "bad_image": args.bad_image,
        "count": args.count,
        "ts_mode": args.ts_mode,
        "custom_ts": args.custom_ts,
        "cam_id": args.cam_id,
        "bucket": args.bucket,
        "prefix": args.prefix,
        "out_dir": args.out_dir,
        # CHANGE: S3 endpoint info
        "s3_endpoint": S3_ENDPOINT,
    }, indent=2))

    if args.mode == "s3":
        inject_to_s3(
            bad_image_path=args.bad_image,
            bucket=args.bucket,
            prefix=args.prefix,
            ts_mode=args.ts_mode,
            cam_id=args.cam_id,
            custom_ts=args.custom_ts,
            count=args.count,
        )
    else:
        inject_to_local(
            bad_image_path=args.bad_image,
            out_dir=args.out_dir,
            ts_mode=args.ts_mode,
            cam_id=args.cam_id,
            custom_ts=args.custom_ts,
            count=args.count,
        )

    print("[BadInjector] Done.")


if __name__ == "__main__":
    main()
