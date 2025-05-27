import os, io, requests
from flask import Flask, request, jsonify
import redis, boto3

app = Flask(__name__)

# ---------- Redis ----------
r = redis.Redis(
    host=os.environ["REDIS_HOST"],
    port=int(os.environ["REDIS_PORT"]),
    decode_responses=True,
)

# ---------- MinIO ----------
s3 = boto3.client(
    "s3",
    endpoint_url=os.environ['MINIO_ENDPOINT'],
    aws_access_key_id=os.environ["MINIO_ACCESS_KEY"],
    aws_secret_access_key=os.environ["MINIO_SECRET_KEY"],
)
BUCKET = os.environ["BUCKET"]

YOLO_ENDPOINT = os.environ["YOLO_ENDPOINT"]


def yolo_remote_count(img_bytes: bytes) -> int:
    """Pošalji sliku na udaljeni YOLOServer, vrati broj auta."""
    files = {"image": ("frame.jpg", io.BytesIO(img_bytes), "image/jpeg")}
    try:
        resp = requests.post(YOLO_ENDPOINT, files=files, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return int(data.get("cars", 0))
    except (requests.RequestException, ValueError):
        return -1   # -1 = greška, možeš logati detaljnije


@app.post("/process")
def process():
    data = request.get_json(force=True)
    key = data["s3_key"]

    # 1. Download slike iz MinIO
    obj = s3.get_object(Bucket=BUCKET, Key=key)
    img_bytes = obj["Body"].read()

    # 2. Remote YOLO inference
    car_cnt = yolo_remote_count(img_bytes)

    # 3. Upis u Redis
    r.hset(f"image:{key}", mapping={"car_count": car_cnt})

    return jsonify({"image": key, "car_count": car_cnt})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)