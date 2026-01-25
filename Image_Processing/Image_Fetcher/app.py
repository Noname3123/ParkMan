import os
import re
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Tuple
import logging

import boto3
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable
import redis
from pymongo import MongoClient


# =========================
# CONFIG (S3/MinIO)
# =========================

# CHANGE: MinIO/S3 endpoint inside docker network (your tests show minio:9901 works)
S3_ENDPOINT = os.getenv("MINIO_ENDPOINT", os.getenv("S3_ENDPOINT", "http://minio:9901"))  # CHANGE
S3_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", os.getenv("S3_ACCESS_KEY", "minioadmin"))  # CHANGE
S3_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", os.getenv("S3_SECRET_KEY", "minioadmin"))  # CHANGE
S3_REGION = os.getenv("S3_REGION", "us-east-1")  # CHANGE

# CHANGE: camera images bucket
S3_BUCKET_NAME = os.getenv("BUCKET_CAMERA", os.getenv("S3_BUCKET_NAME", "camera-images-parking-lot-6953dda6f0f2d22e951cabdb"))  # TODO: Change to your camera-images

# CHANGE: optional prefix
S3_PREFIX = os.getenv("S3_PREFIX", "")  # CHANGE
S3_MAX_KEYS_SCAN = int(os.getenv("S3_MAX_KEYS_SCAN", "5000"))  # CHANGE

# =========================
# CONFIG (Kafka)
# =========================
KAFKA_BROKER = os.getenv("KAFKA_BOOTSTRAP", os.getenv("KAFKA_BROKER", "kafka:9092"))  # CHANGE
KAFKA_TOPIC = os.getenv("TOPIC", os.getenv("KAFKA_TOPIC", "image-topic"))  # CHANGE

# =========================
# CONFIG (Redis)
# =========================
REDIS_HOST = os.getenv("REDIS_HOST", "redis_parking_spots_status")  # CHANGE
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))  # CHANGE
REDIS_DB = int(os.getenv("REDIS_DB", "0"))  # CHANGE

REDIS_KEY_LAST_TS = os.getenv("REDIS_KEY_LAST_TS", "image_fetcher:last_ts")  # CHANGE
REDIS_KEY_LAST_KEY = os.getenv("REDIS_KEY_LAST_KEY", "image_fetcher:last_key")  # CHANGE

# =========================
# CONFIG (Mongo -> parking_lot_id)
# =========================
MONGO_URI = os.getenv("MONGO_MANAGER_DATABASE_R_ONLY_URI", "")  # CHANGE
PARKING_LOT_NAME = os.getenv("PARKING_LOT_NAME", "Zagreb")  # CHANGE
PARKING_LOT_NAME_REGEX = os.getenv("PARKING_LOT_NAME_REGEX", "true").lower() == "true"  # CHANGE

# CHANGE: Mongo collection name for lots (adjust if different)
MONGO_LOTS_COLLECTION = os.getenv("MONGO_LOTS_COLLECTION", "parking_lots")  # CHANGE

# =========================
# Scheduler
# =========================
START_IMMEDIATELY = os.getenv("START_IMMEDIATELY", "true").lower() == "true"  # CHANGE
WRAP_AROUND_TO_START = os.getenv("WRAP_AROUND_TO_START", "true").lower() == "true"  # CHANGE
USE_UTC = True  # CHANGE

# =========================
# Fetching interval (seconds)
# =========================
# If 0, sleep 1 hour (default)
# >0, sleep X seconds (testing)
FETCH_INTERVAL_SECONDS = int(os.getenv("FETCH_INTERVAL_SECONDS", "0"))

# =========================
# Timestamp patterns
# =========================
TS_PATTERNS = [
    re.compile(r"(?P<y>\d{4})[-_/](?P<m>\d{2})[-_/](?P<d>\d{2})[T _-](?P<h>\d{2})[-_:](?P<mi>\d{2})[-_:](?P<s>\d{2})"),
    re.compile(r"(?P<y>\d{4})(?P<m>\d{2})(?P<d>\d{2})[T _-]?(?P<h>\d{2})(?P<mi>\d{2})(?P<s>\d{2})"),
    re.compile(r"(?P<y>\d{4})[/-](?P<m>\d{2})[/-](?P<d>\d{2})[/-](?P<h>\d{2})[/-](?P<mi>\d{2})[/-](?P<s>\d{2})"),
]  # CHANGE


# =========================
# HELPERS
# =========================

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def parse_ts_from_key(key: str) -> Optional[datetime]:
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
    logger = logging.getLogger("ImageFetcher")

    if FETCH_INTERVAL_SECONDS > 0:
        logger.info(
            f"[ImageFetcher] DEV MODE: sleeping {FETCH_INTERVAL_SECONDS}s before next fetch"
        )
        time.sleep(FETCH_INTERVAL_SECONDS)
    else:
        now = datetime.utcnow()
        next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        sleep_seconds = (next_hour - now).total_seconds()

        logger.info(
            f"[ImageFetcher] Sleeping {int(sleep_seconds)}s until next full hour ({next_hour.isoformat()}Z)"
        )
        time.sleep(sleep_seconds)

def list_s3_objects(s3_client, bucket: str, prefix: str, max_keys: int) -> List[str]:
    keys: List[str] = []
    continuation = None

    while True:
        kwargs = {"Bucket": bucket, "MaxKeys": min(1000, max_keys - len(keys))}
        if prefix:
            kwargs["Prefix"] = prefix
        if continuation:
            kwargs["ContinuationToken"] = continuation

        resp = s3_client.list_objects_v2(**kwargs)
        for obj in resp.get("Contents", []):
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
    r.set(REDIS_KEY_LAST_TS, ts.isoformat())
    r.set(REDIS_KEY_LAST_KEY, key)

def resolve_parking_lot_id() -> str:
    if not MONGO_URI:
        raise RuntimeError("Missing MONGO_MANAGER_DATABASE_R_ONLY_URI")

    client = MongoClient(MONGO_URI)
    try:
        db = client.get_default_database()
        if db is None:
            raise RuntimeError("Mongo URI does not include DB name")

        col = db[MONGO_LOTS_COLLECTION]

        if PARKING_LOT_NAME_REGEX:
            q = {"name": {"$regex": PARKING_LOT_NAME, "$options": "i"}}  # CHANGE
        else:
            q = {"name": PARKING_LOT_NAME}  # CHANGE

        doc = col.find_one(q, {"_id": 1, "name": 1})
        if not doc:
            raise RuntimeError(f"Parking lot not found. Query={q}")

        lot_id = str(doc["_id"])
        print(f"[ImageFetcher] Resolved parking_lot_id={lot_id} from Mongo (name='{doc.get('name')}')")
        return lot_id
    finally:
        client.close()


# =========================
# MAIN
# =========================

def main() -> None:
    print("[ImageFetcher] Starting...")

    # Resolve lot once on startup (works because your project targets 1 lot)
    parking_lot_id = resolve_parking_lot_id()

    # S3 client
    s3 = boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,            # CHANGE
        aws_access_key_id=S3_ACCESS_KEY,     # CHANGE
        aws_secret_access_key=S3_SECRET_KEY, # CHANGE
        region_name=S3_REGION,               # CHANGE
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
                print("[ImageFetcher] No parsable timestamp keys found. Nothing to send this hour.")
            else:
                next_key, next_ts = picked

                # CHANGE: payload schema expected by Image Processor
                payload = {
                    "image_key": next_key,          # CHANGE
                    "parking_lot_id": parking_lot_id, # CHANGE
                }

                producer.send(KAFKA_TOPIC, value=payload)
                producer.flush()

                print(f"[ImageFetcher] Sent 1 image to Kafka topic='{KAFKA_TOPIC}': {payload}")

                set_last_state(r, next_ts, next_key)

        except Exception as e:
            print(f"[ImageFetcher] ERROR: {e}")

        sleep_until_next_full_hour()


if __name__ == "__main__":
    main()
