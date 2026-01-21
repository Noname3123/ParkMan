import os, io, json, time, boto3, requests
from confluent_kafka import Consumer, Producer
from PIL import Image, ImageEnhance

# ---- ENV -----------------------------------------------------------
S3 = boto3.client('s3', 
    endpoint_url=os.getenv("MINIO_ENDPOINT"),
    aws_access_key_id=os.getenv("MINIO_ACCESS_KEY"),
    aws_secret_access_key=os.getenv("MINIO_SECRET_KEY")
)
BUCKET_CAMERA = os.getenv("BUCKET_CAMERA", "camera-images")
BUCKET_EDIT = os.getenv("BUCKET_EDIT", "edited-images")
CAR_URL = os.getenv("CAR_COUNTER_URL","http://car-counter:5001/process")

KAFKA_BOOT = os.getenv("KAFKA_BOOTSTRAP","kafka:29092")
TOPIC = os.getenv("TOPIC", "cctv-image-events")

CROP_ENABLED = os.getenv("CROP_ENABLED", "false").lower() in ("1", "true", "yes", "y")
CROP_BOX_RAW = os.getenv("CROP_BOX", "").strip()

# ---- Kafka klijenti -----------------------------------------------
k_cons = Consumer({
    "bootstrap.servers": KAFKA_BOOT,
    "group.id": "image-processor", 
    "auto.offset.reset":"earliest"
    })
k_cons.subscribe([TOPIC])


def parse_crop_box(raw: str, img_w: int, img_h: int):
    """
    raw: "x1,y1,x2,y2"
    vraća tuple (x1,y1,x2,y2) clampan u granice slike ili None ako nije validno
    """
    if not raw:
        return None
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 4:
        return None
    try:
        x1, y1, x2, y2 = map(int, parts)
    except:
        return None

    # clamp u granice slike
    x1 = max(0, min(x1, img_w - 1))
    y1 = max(0, min(y1, img_h - 1))
    x2 = max(1, min(x2, img_w))
    y2 = max(1, min(y2, img_h))

    # mora biti smislen pravokutnik
    if x2 <= x1 or y2 <= y1:
        return None

    return (x1, y1, x2, y2)


def loop():
    for msg in iter(k_cons.poll, None):
        if not msg or msg.error():
            continue
    
        try:
            payload = json.loads(msg.value().decode("utf-8"))
            image_key = payload["image_key"]
            parking_lot_id = payload["parking_lot_id"]
            print(f"[RECV] key: {image_key}, parking_lot_id: {parking_lot_id}")
        except Exception as e:
            print(f"[ERROR] Neispravna poruka: {e}")
            continue

        try:
            # 1. Skini sliku
            img_bytes = S3.get_object(Bucket=BUCKET_CAMERA, Key=image_key)["Body"].read()
            img_id = os.path.splitext(os.path.basename(image_key))[0]
            img = Image.open(io.BytesIO(img_bytes))

            # 2. Spremi neobrađenu sliku u security bucket
            security_bucket = f"safe-storage-parking-lot-{parking_lot_id}"
            S3.put_object(Bucket=security_bucket, Key=f"original/{img_id}.jpg",
                        Body=img_bytes, ContentType="image/jpeg")
            print(f"[SECURE] -> {security_bucket}/original/{img_id}.jpg")

            # 2.5 Crop (samo za daljnju obradu + car-counter)
            work_img = img

            if CROP_ENABLED:
                w, h = img.size
                box = parse_crop_box(CROP_BOX_RAW, w, h)
                if box:
                    work_img = img.crop(box)
                    print(f"[CROP] box={box} orig={w}x{h} cropped={work_img.size}")


            # 3. Obradi sliku (na cropped verziji)
            enhancer = ImageEnhance.Contrast(work_img.convert("RGB"))
            edited_img = enhancer.enhance(1.5)
            edited_bytes = buf.getvalue()

            # 4. Spremanje obrađene slike
            buf = io.BytesIO()
            edited_img.save(buf, format="JPEG")
            buf.seek(0)

            edited_key = f"edited/{img_id}.jpg"
            S3.put_object(Bucket=BUCKET_EDIT, Key=edited_key,
                          Body=edited_bytes, ContentType="image/jpeg")
            print(f"[EDITED] -> {BUCKET_EDIT}/{edited_key}")

            # 5. Slanje Car Counter-u
            resp = requests.post(CAR_URL, json={
                "s3_key": edited_key,
                "parking_lot_id": parking_lot_id
            }, timeout=5)
            resp.raise_for_status()
            print(f"[CAR-COUNTER] response: {resp.json()}")

        except Exception as e:
            print(f"[FAIL] {e}")

if __name__ == "__main__":
    print("Image Processor ready …")
    try:
        loop()
    except KeyboardInterrupt:
        print("Image Processor se gasi (KeyboardInterrupt)...")
    finally:
        print("--- DEBUG: Zatvaram Kafka consumera ---")
        k_cons.close()
        print("Image Processor ugašen.")