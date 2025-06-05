import os, cv2, boto3, random, time
import numpy as np
from io import BytesIO
from PIL import Image

# ---------------- ENV ------------------
S3 = boto3.client(
    's3',
    endpoint_url=os.getenv("MINIO_ENDPOINT"),
    aws_access_key_id=os.getenv("MINIO_ACCESS_KEY"),
    aws_secret_access_key=os.getenv("MINIO_SECRET_KEY")
)
BUCKET = os.getenv("BUCKET_CAMERA", "camera-images")
TEXTURE_FOLDER = "./textures"

# ---------------- EFFECTS ------------------
def apply_blur(img):
    ksize = random.choice([3, 5 ,7])
    return cv2.GaussianBlur(img, (ksize, ksize), 0)

def adjust_brightness(img):
    value = random.uniform(0.5, 1.5)
    return cv2.convertScaleAbs(img, alpha=value, beta=0)

def adjust_contrast(img):
    value = random.uniform(0.5, 1.5)
    return cv2.convertScaleAbs(img, alpha=1.0, beta=int(50* (value- 1)))

def add_noise(img):
    row, col, ch = img.shape
    mean = 0
    sigma = random.randint(5, 25)
    gauss=  np.random.normal(mean, sigma, (row, col, ch)).reshape(row, col, ch).astype(np.uint8)
    return cv2.add(img, gauss)

def overlay_texture(img):
    textures = [f for f in os.listdir(TEXTURE_FOLDER) if f.endswith('.png')]
    if not textures:
        return img
    
    texture_path = os.path.join(TEXTURE_FOLDER, random.choice(textures))
    texture = cv2.imread(texture_path, cv2.IMREAD_UNCHANGED)
    texture = cv2.resize(texture, (img.shape[1], img.shape[0]))

    if texture.shape[2] == 4:
        alpha = texture[:, :, 3] /255.0
        for c in range(3):
            img[:, :,c] = img[:, :, c] * (1 - alpha) + texture[:, :, c] * alpha
        return img.astype(np.uint8)
    return img

# ---------------- MINIO LOAD/SAVE ------------------
def list_images_from_s3():
    response = S3.list_objects_v2(Bucket=BUCKET)
    return [item['Key'] for item in response.get('Contents', []) if item['Key'].lower().endswith(('.jpg', '.jpeg', '.png'))]

def download_image(key):
    obj = S3.get_object(Bucket=BUCKET, Key=key)
    return cv2.imdecode(np.asarray(bytearray(obj['Body'].read()), dtype=np.uint8), cv2.IMREAD_COLOR)

def upload_image(img, original_key, suffix):
    new_key = f"{os.path.splitext(original_key)[0]}_{suffix}.jpg"
    _, buffer = cv2.imencode(".jpg", img)
    S3.put_object(Bucket=BUCKET, Key=new_key, Body=buffer.tobytes(), ContentType="image/jpeg")
    print(f"[INFO] Uploaded: {new_key}")

# ---------------- MAIN LOGIC ------------------
def random_edit_pipeline(img):
    functions = [apply_blur, adjust_brightness, adjust_contrast, add_noise, overlay_texture]
    selected = random.sample(functions, k=random.randint(1, len(functions)))
    for func in selected:
        img = func(img)
    return img, "_".join(func.__name__ for func in selected)

def main():
    try:
        print("[DEBUG] Listening images from S3...")
        image_keys = list_images_from_s3()
        print(f"[DEBUG] Found {len(image_keys)} images.")
        for key in random.sample(image_keys, k=min(len(image_keys), 10)):
            print(f"[INFO] Editing: {key}")
            img = download_image(key)
            edited_img, suffix = random_edit_pipeline(img)
            upload_image(edited_img, key, suffix)
    except Exception as e:
        print(f"[ERROR] Unexpected crash: {e}")

if __name__ == "__main__":
    while True:
        main()
        print("[DEBUG] Waiting 30 seconds before next batch...")
        time.sleep(30)
