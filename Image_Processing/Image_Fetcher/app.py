import os, boto3, time
from confluent_kafka import Producer

# --------- ENVIRONMENT SETUP ---------
S3 = boto3.client(
    's3',
    endpoint_url = os.getenv("MINIO_ENDPOINT"),
    aws_access_key_id = os.getenv("MINIO_ACCESS_KEY"),
    aws_secret_access_key = os.getenv("MINIO_SECRET_KEY")
)
BUCKET = os.getenv("CAMERA_BUCKET", "camera-images")

KAFKA_BOOT = os.getenv("KAFKA_BOOTSTRAP", "kafka:29092")
TOPIC = os.getenv("TOPIC", "cctv-image-events")

producer = Producer({"bootstrap.servers": KAFKA_BOOT})

def send_images_ids():
    response = S3.list_objects_v2(Bucket=BUCKET)
    for obj in response.get('Contents', []):
        image_id = obj['Key']
        print(f"[INFO] Sending image ID to Kafka: {image_id}")
        producer.produce(TOPIC, value=image_id)
        producer.flush()
        time.sleep(1)

if __name__ == "__main__":
    send_images_ids()