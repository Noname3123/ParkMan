import os
import cv2
import random
import shutil
import numpy as np

# ---------- Definiranje putanja ----------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.join(SCRIPT_DIR, "../VisDrone/train")
IMAGES_DIR = os.path.join(BASE_DIR, "images")
LABELS_DIR = os.path.join(BASE_DIR, "labels")
ANNOTATIONS_DIR = os.path.join(BASE_DIR, "annotations")

AUGMENTATIONS = ["blur", "noise", "brightness", "contrast", "gamma"]

# ---------- Funkcije za augmentacije ----------
def add_blur(image):
    return cv2.GaussianBlur(image, (5, 5), 0)

def add_noise(image):
    noise = np.random.normal(0, 25, image.shape).astype(np.float32)
    noisy = image + noise
    noisy = np.clip(noisy, 0, 255).astype(np.uint8)
    return noisy

def adjust_brightness(image):
    return cv2.convertScaleAbs(image, alpha=1, beta=random.randint(30, 80))

def adjust_contrast(image):
    return cv2.convertScaleAbs(image, alpha=random.uniform(1.5, 2.0), beta=0)

def adjust_gamma(image, gamma=1.5):
    invGamma = 1.0 / gamma
    table = np.array([
        ((i / 255.0) ** invGamma) * 255 for i in np.arange(256)
    ]).astype("uint8")
    return cv2.LUT(image, table)

AUGMENT_FUNCTIONS = {
    "blur": add_blur,
    "noise": add_noise,
    "brightness": adjust_brightness,
    "contrast": adjust_contrast,
    "gamma": adjust_gamma
}

# ---------- Glavna funkcija ----------
def augment_dataset():
    for filename in os.listdir(IMAGES_DIR):
        if not filename.lower().endswith(('.jpg', '.png', '.jpeg')):
            continue

        base_name = os.path.splitext(filename)[0]
        image_path = os.path.join(IMAGES_DIR, filename)
        image = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_COLOR)

        if image is None:
            print(f"Greška pri učitavanju {filename}")
            continue

        used_augmentations = random.sample(AUGMENTATIONS, 2)

        for aug_name in used_augmentations:
            aug_image = AUGMENT_FUNCTIONS[aug_name](image)
            new_filename = f"{base_name}_{aug_name}.jpg"
            new_image_path = os.path.join(IMAGES_DIR, new_filename)

            # Spremanje nove slike
            # Dodavanje kompresije: cv2.IMWRITE_JPEG_QUALITY, vrijednost 0-100 (niža vrijednost = veća kompresija)
            cv2.imencode('.jpg', aug_image, [cv2.IMWRITE_JPEG_QUALITY, 50])[1].tofile(new_image_path)

            # Kopiranje label datoteke
            label_src = os.path.join(LABELS_DIR, f"{base_name}.txt")
            label_dst = os.path.join(LABELS_DIR, f"{base_name}_{aug_name}.txt")
            if os.path.exists(label_src):
                shutil.copyfile(label_src, label_dst)

            # Kopiranje annotation datoteke
            annotation_src = os.path.join(ANNOTATIONS_DIR, f"{base_name}.txt")
            annotation_dst = os.path.join(ANNOTATIONS_DIR, f"{base_name}_{aug_name}.txt")
            if os.path.exists(annotation_src):
                shutil.copyfile(annotation_src, annotation_dst)

            print(f"Stvorena: {new_filename}")

if __name__ == "__main__":
    augment_dataset()