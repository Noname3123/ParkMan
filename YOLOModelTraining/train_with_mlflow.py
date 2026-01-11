import torch
from ultralytics import YOLO, settings
import os
from itertools import product
import sys
import mlflow
import mlflow.pytorch
import shutil
import boto3
import logging
import pandas as pd

# -----------------------------------------------------------------------------
# MLflow & MinIO Configuration
# -----------------------------------------------------------------------------

# 1. Set the Tracking URI to the exposed port of the MLflow server
mlflow.set_tracking_uri("http://localhost:5000")

#2. disable ultralytics mlflow integration to avoid conflicts
settings.update({"mlflow": False})

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("train.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# 2. Set S3/MinIO Environment Variables for Artifact Uploads
# The client (this script) needs to know how to talk to MinIO to upload the model.
# NOTE: Ensure these credentials match what is inside ./S3Storage/minio.env
os.environ["MLFLOW_S3_ENDPOINT_URL"] = "http://localhost:9901"  # Port 9901 is mapped in your docker-compose
os.environ["AWS_ACCESS_KEY_ID"] = "minioadmin"      # Default MinIO user
os.environ["AWS_SECRET_ACCESS_KEY"] = "minioadmin"  # Default MinIO password
os.environ["MLFLOW_S3_IGNORE_TLS"] = "true"

# Ensure the MLflow bucket exists in MinIO
try:
    s3 = boto3.client('s3', endpoint_url=os.environ["MLFLOW_S3_ENDPOINT_URL"])
    bucket_name = "mlflow"
    if not any(b['Name'] == bucket_name for b in s3.list_buckets().get('Buckets', [])):
        logger.info(f"Creating S3 bucket: {bucket_name}")
        s3.create_bucket(Bucket=bucket_name)
except Exception as e:
    logger.warning(f"Warning: Attempt to check/create S3 bucket failed: {e}")

# 3. Set the Experiment Name
experiment_name = "YOLO_ParkMan_Training"
try:
    client = mlflow.MlflowClient()
    experiment = client.get_experiment_by_name(experiment_name)
    if experiment and experiment.lifecycle_stage == "deleted":
        client.restore_experiment(experiment.experiment_id)
        logger.info(f"Restored previously deleted experiment: {experiment_name}")
except Exception as e:
    logger.warning(f"Error checking experiment status: {e}")

mlflow.set_experiment(experiment_name)

# -----------------------------------------------------------------------------
# Setup
# -----------------------------------------------------------------------------

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
logger.info(f"Using device: {device}")

data_yaml_path = './VisDrone/data-visdrone.yaml'

param_grid = {
    'epochs': [10],
    'imgsz': [640],
}

# -----------------------------------------------------------------------------
# Training Loop
# -----------------------------------------------------------------------------

if not os.path.exists(data_yaml_path):
    logger.error(f"Error: {data_yaml_path} not found. Please make sure your dataset is correctly placed.")
else:
    for epochs, imgsz in product(param_grid['epochs'], param_grid['imgsz']):
        
        # Define a run name for MLflow
        run_name = f"yolo11m_e{epochs}_img{imgsz}"
        
        # Start an MLflow Run
        with mlflow.start_run(run_name=run_name) as run:
            
            # 1. Log Parameters
            mlflow.log_params({
                "epochs": epochs,
                "imgsz": imgsz,
                "batch_size": 4,
                "model_type": "yolo11m",
                "data_yaml": data_yaml_path,
                "device": str(device)
            })
            
            # 2. Log Dataset Configuration (Versioning)
            mlflow.log_artifact(data_yaml_path, artifact_path="dataset_config")

            # Log the dataset used for this run (populates the 'Datasets' tab in UI)
            ds_info = pd.DataFrame([{"dataset_name": "VisDrone", "yaml_path": os.path.abspath(data_yaml_path)}])
            dataset = mlflow.data.from_pandas(ds_info, name="VisDrone")
            mlflow.log_input(dataset, context="training")

            logger.info(f'_____________________\nepoch: {epochs}, imgsz: {imgsz}, batch: 4____________________\n\n\n')
            
            model = YOLO('./yolo11m.pt')

            # Define custom callback to log metrics during training
            def on_fit_epoch_end(trainer):
                # Log validation metrics (mAP, val losses)
                if trainer.metrics:
                    metrics = {k.replace('(', '_').replace(')', ''): v for k, v in trainer.metrics.items()}
                    mlflow.log_metrics(metrics, step=trainer.epoch)
                
                # Log training losses
                if hasattr(trainer, 'loss_names') and hasattr(trainer, 'tloss'):
                    train_metrics = {f"train_{name}": val.item() for name, val in zip(trainer.loss_names, trainer.tloss)}
                    mlflow.log_metrics(train_metrics, step=trainer.epoch)

                # Log learning rates (pg0, pg1, pg2 usually correspond to weights, biases, etc.)
                if hasattr(trainer, 'optimizer') and trainer.optimizer:
                    for i, param_group in enumerate(trainer.optimizer.param_groups):
                        mlflow.log_metric(f"lr/pg{i}", param_group['lr'], step=trainer.epoch)

                # Log model fitness (weighted combination of mAP metrics used for 'best.pt')
                if hasattr(trainer, 'fitness'):
                    mlflow.log_metric("model_fitness", float(trainer.fitness), step=trainer.epoch)

            model.add_callback("on_fit_epoch_end", on_fit_epoch_end)

            try:
                # Train the model
                # disable  ultralytics mlflow integration to avoid conflicts,
                
                results = model.train(
                    data=data_yaml_path, 
                    epochs=epochs, 
                    imgsz=imgsz, 
                    batch=4, 
                    patience=epochs//2, 
                    single_cls=True,
                    project="runs/train",
                    name=run_name
                )

                # 3. Log Metrics
                # results.results_dict contains final metrics (mAP, loss, etc.)
                metrics = {}
                if hasattr(results, 'results_dict'):
                    # Clean keys (remove parenthesis) for cleaner MLflow UI
                    metrics = {k.replace('(', '_').replace(')', ''): v for k, v in results.results_dict.items()}
                    mlflow.log_metrics(metrics)

                # 4. Log Artifacts (Model Weights & Plots)
                # Log the best model weights
                if hasattr(model.trainer, 'best'):
                    mlflow.log_artifact(model.trainer.best, artifact_path="weights")

                    # Register the model in MLflow Model Registry
                    try:
                        # Load the best model explicitly to ensure we register the best version
                        best_model = YOLO(model.trainer.best)
                        model_info = mlflow.pytorch.log_model(
                            best_model.model, 
                            "model", 
                            registered_model_name="YOLO_ParkMan_visdrone"
                        )

                        # Add description to the registered model version for easier identification in UI
                        client = mlflow.MlflowClient()
                        description = (
                            f"Run ID: {run.info.run_id}\n"
                            f"Epochs: {epochs}, Imgsz: {imgsz}\n"
                            f"mAP50: {metrics.get('metrics/mAP50_B', 'N/A')}"
                        )
                        client.update_model_version(
                            name="YOLO_ParkMan_visdrone",
                            version=model_info.registered_model_version,
                            description=description
                        )
                    except Exception as e:
                        logger.warning(f"Failed to register model: {e}")
                
                # Log training plots (confusion matrix, results.png, etc.) generated by YOLO
                save_dir = model.trainer.save_dir
                for file_name in os.listdir(save_dir):
                    if file_name.endswith('.png') or file_name.endswith('.jpg') or file_name.endswith('.csv'):
                        mlflow.log_artifact(os.path.join(save_dir, file_name), artifact_path="plots")

                logger.info(f"Training results saved to: {save_dir}")

            except Exception as e:
                logger.error(f"Error: {e}")
                mlflow.log_param("error", str(e))

# -----------------------------------------------------------------------------
# Post-Training (Optional: Save best of last run to Drive/Local)
# -----------------------------------------------------------------------------

# Note: 'model' variable holds the last trained model in the loop. 
#if 'model' in locals() and hasattr(model.trainer, 'best'):
 #   best_weights_path = model.trainer.best
  #  drive_save_path = './yolo11m_parkman_weights.pt'
   # shutil.copy(best_weights_path, drive_save_path)
   # print(f"Last run weights saved to disk at: {drive_save_path}")
