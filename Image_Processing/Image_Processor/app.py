import os, json, time, boto3, requests
from confluent_kafka import Consumer, Producer

# ---- ENV -----------------------------------------------------------
S3      = boto3.client('s3', endpoint_url=os.getenv("MINIO_ENDPOINT"),
                       aws_access_key_id=os.getenv("MINIO_ACCESS_KEY"),
                       aws_secret_access_key=os.getenv("MINIO_SECRET_KEY"))
BUCKET   = os.getenv("BUCKET", "camera-images")

KAFKA_BOOT   = os.getenv("KAFKA_BOOT","kafka:29092")
TOPIC        = os.getenv("TOPIC", "cctv-image-events")

CAR_URL      = os.getenv("CAR_COUNTER_URL","http://car-counter:5001/process")

# ---- Kafka klijenti -----------------------------------------------
k_cons = Consumer({"bootstrap.servers": KAFKA_BOOT,
                   "group.id": "image-processor", "auto.offset.reset":"earliest"})
k_cons.subscribe([TOPIC])
k_prod = Producer({"bootstrap.servers": KAFKA_BOOT})

def loop():
    for msg in iter(k_cons.poll, None):
        if not msg or msg.error():
            continue

        raw_bytes = msg.value()
        if not raw_bytes:
            print("Primljena prazna poruka iz Kafke.")
            continue

        try:
            raw_string = raw_bytes.decode('utf-8').strip()
            if not raw_string:
                print("Dekodirana poruka je prazan string.")
                continue

            print(f"Primljeno iz Kafke: '{raw_string}'")
            key = raw_string  # npr. "test.jpg" ili "cam01/test.jpg"
            img_id = os.path.splitext(os.path.basename(key))[0]  # "test"

        except Exception as e:
            print(f"Greška pri obradi poruke: {e}")
            continue

        try:
            # 1) download original
            obj = S3.get_object(Bucket=BUCKET, Key=key)
            img_bytes = obj["Body"].read()

            # 2) kopiraj kao "obrađenu" sliku
            edited_key = f"edited/{img_id}.jpg"
            S3.put_object(Bucket=BUCKET, Key=edited_key,
                          Body=img_bytes, ContentType="image/jpeg")

            # 3) skip Kafka output (onemogućeno)
            note = "ROI cropped, plates blurred, people removed."
            out_evt = {"image_id": img_id, "edited_key": edited_key,
                       "note": note, "ts": int(time.time())}
            # k_prod.produce(TOPIC, json.dumps(out_evt).encode())
            # k_prod.flush()

            # 4) pozovi Car Counter
            try:
                print(CAR_URL)
                requests.post(CAR_URL, json={"s3_key": edited_key}, timeout=3)
            except requests.RequestException as e:
                print("CarCounter unreachable:", e)

        except Exception as e:
            print(f"Greška u procesiranju slike: {e}")

if __name__ == "__main__":
    print("Image Processor ready …")
    try:
        loop()
    except KeyboardInterrupt:
        print("Image Processor se gasi (KeyboardInterrupt)...")
    except Exception as e_main:
        print(f"CRITICAL ERROR u __main__: {e_main}")
        # import traceback
        # traceback.print_exc()
    finally:
        print("--- DEBUG: Zatvaram Kafka consumera ---")
        k_cons.close()
        print("Image Processor ugašen.")