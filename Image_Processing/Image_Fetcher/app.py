import os
import re
import json
import time
import random
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Tuple

import boto3
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable
import redis


# =========================
# CONFIG
# =========================

# CHANGE: S3/MinIO endpoint (http://minio:9000)
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://minio:9000")  # CHANGE
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "minioadmin")      # CHANGE
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "minioadmin")      # CHANGE
S3_REGION = os.getenv("S3_REGION", "us-east-1")               # CHANGE (MinIO ignorira, ali boto3 voli imati)

# CHANGE: Bucket with images
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "camera-images")  # CHANGE

# CHANGE: Prefix to narrow listing (folder naming/structure)
# for example: "2025/12/26/", "parking-lot-1/", "cams/" itd.
S3_PREFIX = os.getenv("S3_PREFIX", "")  # CHANGE

# CHANGE: max number of S3 keys to scan per hour
S3_MAX_KEYS_SCAN = int(os.getenv("S3_MAX_KEYS_SCAN", "5000"))  # CHANGE

# CHANGE: Kafka broker/topic
KAFKA_BROKER = os.getenv("KAFKA_BROKER", "kafka:9092")  # CHANGE
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "image-topic")   # CHANGE

# CHANGE: Redis connection
REDIS_HOST = os.getenv("REDIS_HOST", "redis")  # CHANGE
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))  # CHANGE
REDIS_DB = int(os.getenv("REDIS_DB", "0"))  # CHANGE

# CHANGE: Redis keys for last timestamp and S3 key
REDIS_KEY_LAST_TS = os.getenv("REDIS_KEY_LAST_TS", "image_fetcher:last_ts")       # CHANGE
REDIS_KEY_LAST_KEY = os.getenv("REDIS_KEY_LAST_KEY", "image_fetcher:last_s3_key") # CHANGE

# CHANGE: If true, send immediately on start, otherwise wait until next full hour
START_IMMEDIATELY = os.getenv("START_IMMEDIATELY", "true").lower() == "true"  # CHANGE

# CHANGE:  If true, when reaching the end of available images, wrap around to the start
WRAP_AROUND_TO_START = os.getenv("WRAP_AROUND_TO_START", "true").lower() == "true"  # CHANGE

# CHANGE: Use UTC time for all operations
USE_UTC = True  # CHANGE # if False, uses local time

# CHANGE: Timestamp patterns to parse from S3 keys.
# Order matters - first match is used.
# Modify/add patterns as per your S3 key naming conventions.
TS_PATTERNS = [
    # 2025-12-26_14-05-33 or 2025-12-26 14-05-33 or 2025-12-26T14-05-33
    re.compile(r"(?P<y>\d{4})[-_/](?P<m>\d{2})[-_/](?P<d>\d{2})[T _-](?P<h>\d{2})[-_:](?P<mi>\d{2})[-_:](?P<s>\d{2})"),
    # 20251226_140533 or 20251226-140533
    re.compile(r"(?P<y>\d{4})(?P<m>\d{2})(?P<d>\d{2})[T _-]?(?P<h>\d{2})(?P<mi>\d{2})(?P<s>\d{2})"),
    # folder style: 2025/12/26/14/05/33/anything.jpg
    re.compile(r"(?P<y>\d{4})[/-](?P<m>\d{2})[/-](?P<d>\d{2})[/-](?P<h>\d{2})[/-](?P<mi>\d{2})[/-](?P<s>\d{2})"),
]  # CHANGE


# =========================
# HELPERS
# =========================

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def parse_ts_from_key(key: str) -> Optional[datetime]:
    """
    Try to parse timestamp from S3 key using defined patterns.
    """
    for pattern in TS_PATTERNS:
        m = pattern.search(key)
        if not m:
            continue
        try:
            y = int(m.group("y"))
            mo = int(m.group("m"))
            d = int(m.group("d"))
            h = int(m.group("h"))
            mi = int(m.group("mi"))
            s = int(m.group("s"))
            return datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc)
        except Exception:
            continue
    return None

def sleep_until_next_full_hour() -> None:
    """
    Sleep until the next full hour.
    """
    now = utc_now() if USE_UTC else datetime.now()
    # next full hour
    next_hour = (now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
    seconds = (next_hour - now).total_seconds()
    if seconds < 0:
        seconds = 0
    print(f"[ImageFetcher] Sleeping {int(seconds)}s until next full hour ({next_hour.isoformat()})")
    time.sleep(seconds)

def list_s3_objects(s3_client, bucket: str, prefix: str, max_keys: int) -> List[str]:
    """
    List object keys from S3 using pagination until max_keys reached.
    """
    keys: List[str] = []
    continuation = None

    while True:
        kwargs = {
            "Bucket": bucket,
            "MaxKeys": min(1000, max_keys - len(keys)),
        }
        if prefix:
            kwargs["Prefix"] = prefix
        if continuation:
            kwargs["ContinuationToken"] = continuation

        resp = s3_client.list_objects_v2(**kwargs)
        contents = resp.get("Contents", [])
        for obj in contents:
            k = obj.get("Key")
            if k:
                keys.append(k)
            if len(keys) >= max_keys:
                break

        if len(keys) >= max_keys:
            break

        if resp.get("IsTruncated"):
            continuation = resp.get("NextContinuationToken")
            if not continuation:
                break
        else:
            break

    return keys

def pick_next_key_by_timestamp(keys: List[str], last_ts: Optional[datetime]) -> Optional[Tuple[str, datetime]]:
    """
    From the list of S3 keys:
    - parse timestamps
    - sort by timestamp
    - return first key that is > last_ts
    - if none found and WRAP_AROUND_TO_START=True, return first (oldest)
    """
    parsed: List[Tuple[datetime, str]] = []
    for k in keys:
        ts = parse_ts_from_key(k)
        if ts is None:
            continue
        parsed.append((ts, k))

    parsed.sort(key=lambda x: x[0])

    if not parsed:
        return None

    if last_ts is None:
        ts, k = parsed[0]
        return (k, ts)

    for ts, k in parsed:
        if ts > last_ts:
            return (k, ts)

    # no next found
    if WRAP_AROUND_TO_START:
        ts, k = parsed[0]
        return (k, ts)

    return None

def get_last_state(r: redis.Redis) -> Tuple[Optional[datetime], Optional[str]]:
    last_ts_raw = r.get(REDIS_KEY_LAST_TS)
    last_key_raw = r.get(REDIS_KEY_LAST_KEY)

    last_ts = None
    last_key = None

    if last_ts_raw:
        try:
            # stored as ISO string
            last_ts = datetime.fromisoformat(last_ts_raw.decode("utf-8"))
            if last_ts.tzinfo is None:
                last_ts = last_ts.replace(tzinfo=timezone.utc)
            else:
                last_ts = last_ts.astimezone(timezone.utc)
        except Exception:
            last_ts = None

    if last_key_raw:
        try:
            last_key = last_key_raw.decode("utf-8")
        except Exception:
            last_key = None

    return last_ts, last_key

def set_last_state(r: redis.Redis, ts: datetime, key: str) -> None:
    # CHANGE: store as ISO string
    r.set(REDIS_KEY_LAST_TS, ts.isoformat())
    r.set(REDIS_KEY_LAST_KEY, key)


# =========================
# MAIN
# =========================

def main() -> None:
    print("[ImageFetcher] Starting...")

    # S3 client
    s3 = boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,  # CHANGE
        aws_access_key_id=S3_ACCESS_KEY,  # CHANGE
        aws_secret_access_key=S3_SECRET_KEY,  # CHANGE
        region_name=S3_REGION,  # CHANGE
    )

    # Redis
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=False)  # CHANGE

    # Kafka producer
    producer = None
    while producer is None:
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BROKER,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
        except NoBrokersAvailable:
            print(f"[ImageFetcher] Kafka broker not available at {KAFKA_BROKER}. Retrying in 5s...")
            time.sleep(5)

    if not START_IMMEDIATELY:
        sleep_until_next_full_hour()

    while True:
        try:
            last_ts, last_key = get_last_state(r)
            print(f"[ImageFetcher] Last state: last_ts={last_ts}, last_key={last_key}")

            keys = list_s3_objects(s3, S3_BUCKET_NAME, S3_PREFIX, S3_MAX_KEYS_SCAN)
            print(f"[ImageFetcher] Listed {len(keys)} keys from bucket='{S3_BUCKET_NAME}' prefix='{S3_PREFIX}'")

            picked = pick_next_key_by_timestamp(keys, last_ts)
            if not picked:
                # no parsable timestamps found
                print("[ImageFetcher] No parsable timestamp keys found. Nothing to send this hour.")
            else:
                next_key, next_ts = picked
                # CHANGE: prepare payload
                payload = {
                    "bucket": S3_BUCKET_NAME,            # CHANGE
                    "s3_key": next_key,                  # CHANGE
                    "timestamp_utc": next_ts.isoformat() # CHANGE
                    # CHANGE: add more metadata if needed
                }

                producer.send(KAFKA_TOPIC, value=payload)
                producer.flush()

                print(f"[ImageFetcher] Sent 1 image to Kafka topic='{KAFKA_TOPIC}': {payload}")

                # update state
                set_last_state(r, next_ts, next_key)

        except Exception as e:
            print(f"[ImageFetcher] ERROR: {e}")

        # Sleep until next full hour
        sleep_until_next_full_hour()


if __name__ == "__main__":
    main()
