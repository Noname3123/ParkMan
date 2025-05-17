import os, json, time, boto3, requests
from confluent_kafka import Consumer, Producer

# ---- ENV -----------------------------------------------------------
S3      = boto3.client('s3', endpoint_url=os.getenv("MINIO_ENDPOINT"),
                       aws_access_key_id=os.getenv("MINIO_ACCESS_KEY"),
                       aws_secret_access_key=os.getenv("MINIO_SECRET_KEY"))
BUCKET   = os.getenv("BUCKET", "camera-images")

KAFKA_BOOT   = os.getenv("KAFKA_BOOTSTRAP","kafka:29092")
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
        if not raw_bytes: # Provjeri jesu li bytes uopće primljeni
            print("Primljena prazna poruka iz Kafke.")
            continue

        try:
            # Dekodiraj bytes u string (pretpostavljamo UTF-8 enkoding)
            raw_string = raw_bytes.decode('utf-8')
            if not raw_string.strip(): # Provjeri je li dekodirani string prazan ili samo whitespace
                print("Dekodirana poruka je prazan string.")
                continue
            ev = json.loads(raw_string)
        except UnicodeDecodeError as e:
            print(f"Greška pri dekodiranju poruke iz Kafke: {e}")
            print(f"Problematični bytes: {raw_bytes}")
            continue
        except json.JSONDecodeError as e:
            print(f"Greška pri parsiranju JSON-a: {e}")
            print(f"Problematični string: {raw_string}")
            continue

        key = ev["key"]          # npr. cam01/123.jpg
        img_id = ev["image_id"]

        # 1) download original
        obj = S3.get_object(Bucket=BUCKET, Key=key)
        img_bytes = obj["Body"].read()

        # 2) "fake edit" – samo kopiraj u drugi bucket pod novim imenom
        edited_key = f"edited/{img_id}.jpg"
        S3.put_object(Bucket=BUCKET, Key=edited_key,
                      Body=img_bytes, ContentType="image/jpeg")

        # 3) pošalji metapodatke na Kafka
        note = "ROI cropped, plates blurred, people removed."
        out_evt = {"image_id": img_id, "edited_key": edited_key,
                   "note": note, "ts": int(time.time())}
        k_prod.produce(TOPIC, json.dumps(out_evt).encode())
        k_prod.flush()

        # 4) trigger Car Counter
        try:
            requests.post(CAR_URL, json={"s3_key": edited_key}, timeout=3)
        except requests.RequestException as e:
            print("CarCounter unreachable:", e)

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