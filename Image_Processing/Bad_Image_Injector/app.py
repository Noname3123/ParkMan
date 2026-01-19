import os
import sys
import json
import uuid
import argparse
from datetime import datetime, timezone
from typing import Optional

import boto3


# ============================================================
# Bad Image Injector (S3/MinIO + Local)
# ============================================================
# Uloga:
# - Namjerno ubaciti "lošu" sliku (npr. prazan parking) u ingestion bucket
# - kako bi testirao alerting/drift/anomaly pipeline.
#
# Usklađenje s projektom:
# - koristi MINIO_* i BUCKET_CAMERA iz Image_Processing/.env
# - naming ključeva kompatibilan s Image Fetcher timestamp parsiranjem
#
# Modo-vi:
# - --mode s3    : upload u MinIO/S3
# - --mode local : upis u lokalni folder (za test)
# ============================================================


# =========================
# CONFIG (ENV) - MinIO/S3
# =========================

# CHANGE: preferiraj MINIO_* iz Image_Processing/.env, fallback na stare S3_*
S3_ENDPOINT = os.getenv("MINIO_ENDPOINT", os.getenv("S3_ENDPOINT", "http://minio:9901"))  # CHANGE
S3_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", os.getenv("S3_ACCESS_KEY", "minioadmin"))  # CHANGE
S3_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", os.getenv("S3_SECRET_KEY", "minioadmin"))  # CHANGE
S3_REGION = os.getenv("S3_REGION", "us-east-1")  # CHANGE

# CHANGE: default bucket za ingestion slike
DEFAULT_BUCKET = os.getenv("BUCKET_CAMERA", os.getenv("S3_BUCKET_NAME", "camera-images"))  # CHANGE

# CHANGE: default prefix u bucketu (ako želite sve pod npr. "cams/" ili "prod/")
DEFAULT_PREFIX = os.getenv("S3_PREFIX", "")  # CHANGE

# CHANGE: default lokalni output folder
DEFAULT_LOCAL_OUT = os.getenv("LOCAL_OUT_DIR", "./_inject_out")  # CHANGE

# CHANGE: default putanja do bad slike
DEFAULT_BAD_IMAGE_PATH = os.getenv("BAD_IMAGE_PATH", "./bad_samples/empty_parking.jpg")  # CHANGE


# =========================
# Timestamp helpers
# =========================

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def floor_to_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


# =========================
# Key naming (S3 key)
# =========================

def build_object_key(prefix: str, ts: datetime, ext: str, cam_id: Optional[str] = None, index: int = 0) -> str:
    """
    Željeni format (bez foldera):
      parking_spot_YYYY-MM-DD_HH-MM-SS.jpg
    Ako count > 1, dodajemo sufiks _01, _02... da se ne prepisuju.
    """
    # osiguraj UTC
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    else:
        ts = ts.astimezone(timezone.utc)

    base = f"parking_spot_{ts.year:04d}-{ts.month:02d}-{ts.day:02d}_{ts.hour:02d}-{ts.minute:02d}-{ts.second:02d}"

    # da se ne prepisuje ako count > 1
    if index > 0:
        base = f"{base}_{index:02d}"

    fname = f"{base}{ext}"

    if prefix and not prefix.endswith("/"):
        prefix += "/"

    return f"{prefix}{fname}"



# =========================
# S3 client + utils
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
    CHANGE: Ako ne želiš auto-create bucket, makni ovu funkciju iz poziva.
    """
    try:
        s3.head_bucket(Bucket=bucket)
    except Exception:
        s3.create_bucket(Bucket=bucket)


# =========================
# File helpers
# =========================

def read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()

def infer_ext(path: str) -> str:
    _, ext = os.path.splitext(path)
    return ext if ext else ".jpg"  # CHANGE: default

def content_type_for_ext(ext: str) -> str:
    """
    CHANGE: ako kasnije budete koristili png/webp, ovo pomaže.
    """
    e = ext.lower()
    if e in [".jpg", ".jpeg"]:
        return "image/jpeg"
    if e == ".png":
        return "image/png"
    if e == ".webp":
        return "image/webp"
    return "application/octet-stream"  # fallback


# =========================
# Injection: S3
# =========================

def inject_to_s3(
    bad_image_path: str,
    bucket: str,
    prefix: str,
    ts_mode: str,
    custom_ts: Optional[str],
    cam_id: Optional[str],
    count: int,
) -> None:
    """
    Injecta count slika u MinIO/S3.

    ts_mode:
      - now    : koristi trenutni UTC timestamp
      - hour   : koristi timestamp na početku trenutnog sata (HH:00:00)
      - custom : koristi custom ISO timestamp
    """
    s3 = get_s3_client()
    ensure_bucket_exists(s3, bucket)

    data = read_bytes(bad_image_path)
    ext = infer_ext(bad_image_path)
    ctype = content_type_for_ext(ext)

    for i in range(count):
        # odabir timestampa
        if ts_mode == "now":
            ts = utc_now()
        elif ts_mode == "hour":
            ts = floor_to_hour(utc_now())
        elif ts_mode == "custom":
            if not custom_ts:
                raise ValueError("custom_ts is required when ts_mode=custom")
            # CHANGE: podrška za "Z"
            iso = custom_ts.replace("Z", "+00:00")
            ts = datetime.fromisoformat(iso)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            else:
                ts = ts.astimezone(timezone.utc)
        else:
            raise ValueError(f"Unknown ts_mode: {ts_mode}")

        key = build_object_key(prefix=prefix, ts=ts, ext=ext, cam_id=cam_id, index=i)

        # CHANGE: metadata (korisno za debug / filtriranje)
        metadata = {
            "injected": "true",                  # CHANGE
            "inject_reason": "bad_image_test",   # CHANGE
            "inject_ts_utc": utc_now().isoformat()
        }

        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=data,
            ContentType=ctype,
            Metadata=metadata,
        )

        print(f"[BadInjector] Uploaded bad image to s3://{bucket}/{key}")


# =========================
# Injection: Local
# =========================

def inject_to_local(
    bad_image_path: str,
    out_dir: str,
    ts_mode: str,
    custom_ts: Optional[str],
    cam_id: Optional[str],
    count: int,
) -> None:
    """
    Local upis koristi ISTI naming kao S3 (kreira foldere).
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
            iso = custom_ts.replace("Z", "+00:00")
            ts = datetime.fromisoformat(iso)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            else:
                ts = ts.astimezone(timezone.utc)
        else:
            raise ValueError(f"Unknown ts_mode: {ts_mode}")

        rel_path = build_object_key(prefix="", ts=ts, ext=ext, cam_id=cam_id)
        local_path = os.path.join(out_dir, rel_path)
        os.makedirs(os.path.dirname(local_path), exist_ok=True)

        with open(local_path, "wb") as f:
            f.write(data)

        print(f"[BadInjector] Wrote bad image to {local_path}")


# =========================
# CLI
# =========================

def parse_args():
    p = argparse.ArgumentParser(description="Bad Image Injector (S3/Local)")

    # CHANGE: default mode
    p.add_argument("--mode", choices=["s3", "local"], default="s3")  # CHANGE

    p.add_argument("--bad-image", default=DEFAULT_BAD_IMAGE_PATH, help="Path to bad image file")  # CHANGE
    p.add_argument("--count", type=int, default=1, help="How many images to inject")  # CHANGE

    p.add_argument("--ts-mode", choices=["now", "hour", "custom"], default="now", help="Timestamp mode")  # CHANGE
    p.add_argument("--custom-ts", default=None, help="Custom ISO timestamp e.g. 2026-01-12T18:00:00Z")  # CHANGE
    p.add_argument("--cam-id", default=None, help="Optional camera id to embed in filename")  # CHANGE

    # S3 args
    p.add_argument("--bucket", default=DEFAULT_BUCKET, help="Bucket to inject into")  # CHANGE
    p.add_argument("--prefix", default=DEFAULT_PREFIX, help="Prefix (folder root) inside bucket")  # CHANGE

    # Local args
    p.add_argument("--out-dir", default=DEFAULT_LOCAL_OUT, help="Local output dir")  # CHANGE

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
        "minio_endpoint": S3_ENDPOINT,  # read from env
    }, indent=2))

    if args.mode == "s3":
        inject_to_s3(
            bad_image_path=args.bad_image,
            bucket=args.bucket,
            prefix=args.prefix,
            ts_mode=args.ts_mode,
            custom_ts=args.custom_ts,
            cam_id=args.cam_id,
            count=args.count,
        )
    else:
        inject_to_local(
            bad_image_path=args.bad_image,
            out_dir=args.out_dir,
            ts_mode=args.ts_mode,
            custom_ts=args.custom_ts,
            cam_id=args.cam_id,
            count=args.count,
        )

    print("[BadInjector] Done.")

if __name__ == "__main__":
    main()
