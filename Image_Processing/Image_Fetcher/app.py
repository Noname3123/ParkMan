import os
import re
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Tuple

import boto3
from kafka import KafkaProducer
import redis

from pymongo import MongoClient
from bson import ObjectId


# ============================================================
# Image Fetcher (timestamp-ordered, hourly, Mongo parking_lot_id)
# ============================================================
# Uloga:
# - Svaki puni sat (UTC) pošalje TOČNO 1 sliku u Kafka topic
# - Slika se bira redom po timestamp-u iz S3 key-a
# - parking_lot_id se dohvaća iz MongoDB (Manager DB) po imenu parking lota
# - State (last_ts, last_key, cached parking_lot_id) je u Redis-u
#
# Važno (usklađenje s projektom):
# - Koristi MINIO_* env varijable (fallback na stare S3_*)
# - Koristi KAFKA_BOOTSTRAP i TOPIC (fallback na stare KAFKA_*)
# - Koristi BUCKET_CAMERA (fallback na S3_BUCKET_NAME)
# - Kafka payload mora sadržavati: image_key, parking_lot_id (Image_Processor to očekuje)
# ============================================================


# =========================
# CONFIG (ENV) - MinIO/S3
# =========================

# CHANGE: preferiraj MINIO_* iz Image_Processing/.env, ali ostavi fallback na stare varijable
S3_ENDPOINT = os.getenv("MINIO_ENDPOINT", os.getenv("S3_ENDPOINT", "http://minio:9901"))  # CHANGE
S3_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", os.getenv("S3_ACCESS_KEY", "minioadmin"))  # CHANGE
S3_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", os.getenv("S3_SECRET_KEY", "minioadmin"))  # CHANGE
S3_REGION = os.getenv("S3_REGION", "us-east-1")  # CHANGE (MinIO ignorira, boto3 voli imati)

# CHANGE: bucket iz kojeg čitaš slike
S3_BUCKET_NAME = os.getenv("BUCKET_CAMERA", os.getenv("S3_BUCKET_NAME", "camera-images"))  # CHANGE

# CHANGE: prefix koji sužava listing (preporučeno kad standardizirate naming/foldere)
S3_PREFIX = os.getenv("S3_PREFIX", "")  # CHANGE

# CHANGE: maksimalan broj objekata za skeniranje po satu (sigurnosno ograničenje)
S3_MAX_KEYS_SCAN = int(os.getenv("S3_MAX_KEYS_SCAN", "5000"))  # CHANGE


# =========================
# CONFIG (ENV) - Kafka
# =========================

# CHANGE: preferiraj KAFKA_BOOTSTRAP i TOPIC iz .env
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", os.getenv("KAFKA_BROKER", "kafka:29092"))  # CHANGE
KAFKA_TOPIC = os.getenv("TOPIC", os.getenv("KAFKA_TOPIC", "cctv-image-events"))           # CHANGE


# =========================
# CONFIG (ENV) - Redis (state)
# =========================

REDIS_HOST = os.getenv("REDIS_HOST", "redis_parking_spots_status")  # CHANGE
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))                   # CHANGE
REDIS_DB = int(os.getenv("REDIS_DB", "0"))                          # CHANGE

# CHANGE: Redis keys (namespaced)
REDIS_KEY_LAST_TS = os.getenv("REDIS_KEY_LAST_TS", "image_fetcher:last_ts")            # CHANGE
REDIS_KEY_LAST_KEY = os.getenv("REDIS_KEY_LAST_KEY", "image_fetcher:last_s3_key")      # CHANGE
REDIS_KEY_LOT_ID = os.getenv("REDIS_KEY_LOT_ID", "image_fetcher:parking_lot_id")       # CHANGE

# CHANGE: koliko dugo cacheamo parking_lot_id (sekunde). 0 = bez TTL (stalno)
PARKING_LOT_ID_CACHE_TTL = int(os.getenv("PARKING_LOT_ID_CACHE_TTL", "3600"))          # CHANGE


# =========================
# CONFIG (ENV) - Mongo (Manager DB)
# =========================

# CHANGE: Mongo read-only URI iz .env
MONGO_URI = os.getenv("MONGO_MANAGER_DATABASE_R_ONLY_URI", "")  # CHANGE

# CHANGE: ime parking lota kreiranog skriptom create_specific_lot.py
PARKING_LOT_NAME = os.getenv("PARKING_LOT_NAME", "Zagreb City Center Garage")  # CHANGE

# CHANGE: ako true, koristi regex pretragu (contains) umjesto exact match
PARKING_LOT_NAME_REGEX = os.getenv("PARKING_LOT_NAME_REGEX", "false").lower() == "true"  # CHANGE


# =========================
# RUNTIME OPTIONS
# =========================

# CHANGE: ako true, šalje odmah na startu, inače čeka sljedeći puni sat
START_IMMEDIATELY = os.getenv("START_IMMEDIATELY", "true").lower() == "true"  # CHANGE

# CHANGE: ako true, kad dođe do kraja slika, vraća se na početak
WRAP_AROUND_TO_START = os.getenv("WRAP_AROUND_TO_START", "true").lower() == "true"  # CHANGE

# CHANGE: radi deterministički u UTC
USE_UTC = True  # CHANGE


# =========================
# TIMESTAMP PARSING (KEY -> datetime)
# =========================

# CHANGE: ovo prilagodi kad znate točan naming key-eva
TS_PATTERNS = [
    # 2025-12-26_14-05-33 or 2025-12-26 14-05-33 or 2025-12-26T14-05-33
    re.compile(r"(?P<y>\d{4})[-_/](?P<m>\d{2})[-_/](?P<d>\d{2})[T _-](?P<h>\d{2})[-_:](?P<mi>\d{2})[-_:](?P<s>\d{2})"),
    # 20251226_140533 or 20251226-140533
    re.compile(r"(?P<y>\d{4})(?P<m>\d{2})(?P<d>\d{2})[T _-]?(?P<h>\d{2})(?P<mi>\d{2})(?P<s>\d{2})"),
    # folder style: 2025/12/26/14/05/33/anything.jpg
    re.compile(r"(?P<y>\d{4})[/-](?P<m>\d{2})[/-](?P<d>\d{2})[/-](?P<h>\d{2})[/-](?P<mi>\d{2})[/-](?P<s>\d{2})"),
]  # CHANGE


def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def parse_ts_from_key(key: str) -> Optional[datetime]:
    """
    Pokušava izvući timestamp iz S3 key-a koristeći TS_PATTERNS.
    Vraća datetime u UTC.
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


# =========================
# SCHEDULING
# =========================

def sleep_until_next_full_hour() -> None:
    """
    Spava do idućeg punog sata (UTC).
    """
    now = utc_now() if USE_UTC else datetime.now()
    next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    seconds = max(0, (next_hour - now).total_seconds())
    print(f"[ImageFetcher] Sleeping {int(seconds)}s until next full hour ({next_hour.isoformat()})")
    time.sleep(seconds)


# =========================
# S3 LISTING + PICK NEXT
# =========================

def list_s3_objects(s3_client, bucket: str, prefix: str, max_keys: int) -> List[str]:
    """
    List object keys from S3 using pagination until max_keys reached.
    """
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
    """
    - parsira timestamp iz key-a
    - sortira po timestampu
    - vrati prvi koji je > last_ts
    - ako nema, i WRAP_AROUND_TO_START=True, vrati najstariji
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

    if WRAP_AROUND_TO_START:
        ts, k = parsed[0]
        return (k, ts)

    return None


# ====================
