import os, io, requests, datetime
from flask import Flask, request, jsonify
import redis, boto3

app = Flask(__name__)

# ---------- Redis ----------
r = redis.Redis(
    host=os.getenv("REDIS_HOST"),
    port=int(os.getenv("REDIS_PORT")),
    decode_responses=True,
)

# ---------- MinIO ----------
s3 = boto3.client(
    "s3",
    endpoint_url=os.getenv('MINIO_ENDPOINT'),
    aws_access_key_id=os.getenv("MINIO_ACCESS_KEY"),
    aws_secret_access_key=os.getenv("MINIO_SECRET_KEY"),
)
BUCKET = os.getenv("BUCKET_EDIT")

YOLO_ENDPOINT = os.getenv("YOLO_ENDPOINT", "http://yolo_server:8000/predict")


def yolo_remote_count(img_bytes: bytes) -> int:
    """Pošalji sliku na udaljeni YOLOServer, vrati broj auta."""
    files = {"file": ("frame.jpg", io.BytesIO(img_bytes), "image/jpeg")}
    try:
        resp = requests.post(YOLO_ENDPOINT, files=files, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return int(data.get("car_count", 0))
    except (requests.RequestException, ValueError):
        return -1   # -1 = greška, možeš logati detaljnije


@app.post("/process")
def process():
    data = request.get_json(force=True)
    key = data["s3_key"]
    lot_id = data["parking_lot_id"]

    # 1. Preuzmi sliku iz S3
    obj = s3.get_object(Bucket=BUCKET, Key=key)
    img_bytes = obj["Body"].read()

    # 2. Pošalji YOLO servisu
    car_cnt = yolo_remote_count(img_bytes)
    print(f"[YOLO] {car_cnt} auta detektirano za lot {lot_id}")

    # 3. Upis u Redis
    try:
        r.hset(f"parking_lot:{lot_id}", mapping={
            "car_num": str(car_cnt),
        })
        print(f"[REDIS] Ažurirano parking_lot:{lot_id} -> {car_cnt} auta")
    except redis.exceptions.RedisError as e:
        print(f"[REDIS ERROR] {e}")

    return jsonify({
        "image": key,
        "car_count": car_cnt,
        "parking_lot_id": lot_id
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)