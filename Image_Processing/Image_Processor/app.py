import os, uuid, tempfile
from flask import Flask, request, jsonify
import boto3, requests

app = Flask(__name__)

# ---------- MinIO ----------
s3 = boto3.client(
    "s3",
    endpoint_url=f"http://{os.environ['MINIO_ENDPOINT']}",
    aws_access_key_id=os.environ["MINIO_ACCESS_KEY"],
    aws_secret_access_key=os.environ["MINIO_SECRET_KEY"],
)
BUCKET = os.environ["MINIO_BUCKET"]

CAR_COUNTER_URL = "http://car_counter:5000/process"

@app.post("/ingest")
def ingest():
    file = request.files.get("image")
    if not file or not file.mimetype.startswith("image"):
        return jsonify({"error": "No image uploaded"}), 400

    ext = os.path.splitext(file.filename)[1] or ".jpg"
    key = f"{uuid.uuid4()}{ext}"

    # Spremi lokalno -> MinIO
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        file.save(tmp.name)
        s3.upload_file(tmp.name, BUCKET, key)
    os.unlink(tmp.name)

    # Obavijesti car_counter (fire‑and‑forget)
    try:
        requests.post(CAR_COUNTER_URL, json={"s3_key": key}, timeout=2)
    except requests.RequestException:
        pass

    return jsonify({"status": "stored", "s3_key": key})