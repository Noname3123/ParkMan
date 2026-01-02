import os
import io
from fastapi import FastAPI, UploadFile, File
import uvicorn
from ultralytics import YOLO
from PIL import Image
import gdown

app = FastAPI()

# Configuration
MODEL_FILE = "yolo11m_parkman_weights.pt"
FILE_ID = "1p1xAfbgcQoMWaLc_Rg13lqAQs8c8O1US"

def load_model():
    if not os.path.exists(MODEL_FILE):
        print(f"Downloading model {MODEL_FILE}...")
        url = f'https://drive.google.com/uc?id={FILE_ID}'
        gdown.download(url, output=MODEL_FILE, quiet=False)
    
    print(f"Loading model {MODEL_FILE}...")
    return YOLO(MODEL_FILE)

model = load_model()

def get_target_class_count(results, target_class_name):
    target_class_count = 0
    for box in results[0].boxes:
        class_id = int(box.cls[0])
        detected_class_name = model.names[class_id]
        if detected_class_name == target_class_name:
            target_class_count += 1
    return target_class_count

@app.post("/predict")
async def predict(file: UploadFile = File(...)):
    try:
        image_data = await file.read()
        image = Image.open(io.BytesIO(image_data))
        
        results = model(image)
        # 'space-occupied' is the class name used in the notebook
        car_count = get_target_class_count(results, 'space-occupied')
        
        return {"car_count": car_count}
    except Exception as e:
        return {"error": str(e), "car_count": -1}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)