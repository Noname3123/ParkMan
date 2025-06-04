import os, boto3, random, json, time
from confluent_kafka import Producer
from pymongo import MongoClient

# --------- ENVIRONMENT SETUP ---------
S3 = boto3.client(
    's3',
    endpoint_url = os.getenv("MINIO_ENDPOINT"),
    aws_access_key_id = os.getenv("MINIO_ACCESS_KEY"),
    aws_secret_access_key = os.getenv("MINIO_SECRET_KEY")
)
BUCKET = os.getenv("BUCKET_CAMERA", "camera-images")

MONGO_MANAGER_DATABASE_R_ONLY_URI = os.getenv("MONGO_MANAGER_DATABASE_R_ONLY_URI", "mongodb://external:external_pass@mongo_manager_db_service:27017/ParkMan_manager_db")
KAFKA_BOOT = os.getenv("KAFKA_BOOTSTRAP", "kafka:29092")
TOPIC = os.getenv("TOPIC", "cctv-image-events")

producer = Producer({"bootstrap.servers": KAFKA_BOOT})

mongo = MongoClient(MONGO_MANAGER_DATABASE_R_ONLY_URI)
collection = mongo.ParkMan_manager_db.parking_lots

def get_random_s3_key():
    response = S3.list_objects_v2(Bucket=BUCKET)
    contents = response.get("Contents", [])
    if not contents:
        return None
    return random.choice(contents)["Key"]

def get_random_parking_lot_id():
    docs = list(collection.find({}, {"_id": 1}))
    if not docs:
        return None
    return str(random.choice(docs)["_id"])

def send_message():
    image_key = get_random_s3_key()
    parking_lot_id = get_random_parking_lot_id()

    if not image_key or not parking_lot_id:
        print("[ERROR] Nema slike ili parkinga.")
        return
    
    msg = {
        "image_key": image_key,
        "parking_lot_id": parking_lot_id
    }

    producer.produce(TOPIC, json.dumps(msg).encode("utf-8"))
    producer.flush()
    print(f"[SENT] {msg}")

if __name__ == "__main__":
    while True:
        send_message()
        print("[DEBUG] Waiting 50 seconds before next messages...")
        time.sleep(50)
