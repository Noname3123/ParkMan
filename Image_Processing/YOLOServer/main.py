import os
import io
from fastapi import FastAPI, UploadFile, File
import uvicorn
from ultralytics import YOLO
import torch
from PIL import Image
import mlflow
from mlflow.tracking import MlflowClient
import mlflow.pytorch
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# Configuration
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow_server:5000")
MODEL_NAME = os.getenv("MLFLOW_MODEL_NAME", "YOLO_ParkMan_visdrone")
MODEL_TAG = os.getenv("MLFLOW_MODEL_TAG", "best_stability")

def load_model():
    print(f"Connecting to MLflow at {MLFLOW_TRACKING_URI}...")
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    
    print(f"Loading model '{MODEL_NAME}' with tag '{MODEL_TAG}'...")
    try:
        # Construct the model URI for the registry (e.g., models:/ParkManYOLO/Production)
        model_uri = f"models:/{MODEL_NAME}@{MODEL_TAG}"
        return mlflow.pytorch.load_model(model_uri)
    except Exception as e:
        print(f"Error loading model from MLflow: {e}")
        raise e

try:
    model = load_model()
except Exception:
    model = None

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
    if model is None:
        return {"error": "Model not loaded", "car_count": -1}

    try:
        image_data = await file.read()
        image = Image.open(io.BytesIO(image_data))
        
        # Force inference on GPU if available (since model was saved on CPU)
        results = model(image, device=0 if torch.cuda.is_available() else "cpu")
        # 'space-occupied' is the class name used in the notebook
        car_count = get_target_class_count(results, 'item')
        
        return {"car_count": car_count}
    except Exception as e:
        return {"error": str(e), "car_count": -1}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)