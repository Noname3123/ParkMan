import tempfile
import torch
from ultralytics import YOLO, settings
import os
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
os.environ["MLFLOW_KEEP_RUN_ACTIVE"] = "true"

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

data_yaml_path = './VisDrone/data-romania.yaml'

training_configs = [
    # Config 1
    {
        'imgsz': 640, 'epochs': 50, 'batch': -1, 'lr0': 0.01, 'lrf': 0.01,
        'optimizer': 'SGD', 'weight_decay': 0.0005, 'warmup_epochs': 3, 'cos_lr': False,
        'hsv_h': 0.015, 'hsv_s': 0.7, 'hsv_v': 0.4, 'degrees': 0.0, 'translate': 0.1,
        'scale': 0.5, 'shear': 0.0, 'fliplr': 0.5, 'flipud': 0.0, 'mosaic': 1.0,
        'mixup': 0.0, 'copy_paste': 0.0, 'patience': 20
    },
    # Config 2
    {
        'imgsz': 640, 'epochs': 80, 'batch': -1, 'lr0': 0.008, 'lrf': 0.05,
        'optimizer': 'SGD', 'weight_decay': 0.0007, 'warmup_epochs': 4, 'cos_lr': True,
        'translate': 0.08, 'scale': 0.4, 'mosaic': 0.7, 'mixup': 0.0, 'copy_paste': 0.0,
        'fliplr': 0.6, 'patience': 25
    },
    # Config 3
    {
        'imgsz': 768, 'epochs': 100, 'batch': -1, 'lr0': 0.0035, 'lrf': 0.1,
        'optimizer': 'AdamW', 'weight_decay': 0.01, 'warmup_epochs': 5, 'cos_lr': True,
        'hsv_h': 0.015, 'hsv_s': 0.6, 'hsv_v': 0.35, 'translate': 0.06, 'scale': 0.35,
        'mosaic': 0.5, 'mixup': 0.05, 'copy_paste': 0.0, 'patience': 30
    },
    # Config 4
    {
        'imgsz': 768, 'epochs': 130, 'batch': -1, 'lr0': 0.0025, 'lrf': 0.12,
        'optimizer': 'AdamW', 'weight_decay': 0.012, 'warmup_epochs': 6, 'cos_lr': True,
        'hsv_s': 0.7, 'hsv_v': 0.45, 'translate': 0.07, 'scale': 0.4, 'mosaic': 0.35,
        'mixup': 0.10, 'copy_paste': 0.1, 'close_mosaic': 15, 'patience': 35
    },
    # Config 5
    {
        'imgsz': 960, 'epochs': 160, 'batch': -1, 'lr0': 0.0020, 'lrf': 0.15,
        'optimizer': 'AdamW', 'weight_decay': 0.015, 'warmup_epochs': 8, 'cos_lr': True,
        'mosaic': 0.25, 'mixup': 0.05, 'copy_paste': 0.05, 'translate': 0.05,
        'scale': 0.3, 'fliplr': 0.5, 'close_mosaic': 25, 'patience': 40
    }
]

MODEL_TYPE = 'yolo11s'

#.---------------------
#helper functions
#.---------------------

def clean_YOLO_model(model: YOLO) -> YOLO:
    """
    Save model to temporary location and reload it. This removes training artifacts and data loaders.
    """
    with tempfile.NamedTemporaryFile(suffix='.pt', delete=False) as tmp:
        model.save(tmp.name)
        # Create a fresh YOLO instance from the saved weights
        clean_model = YOLO(tmp.name)
        return clean_model

# -----------------------------------------------------------------------------
# Training Loop
# -----------------------------------------------------------------------------

if not os.path.exists(data_yaml_path):
    logger.error(f"Error: {data_yaml_path} not found. Please make sure your dataset is correctly placed.")
else:
    for i, config in enumerate(training_configs):

        # Define a run name for MLflow
        run_name = f"{MODEL_TYPE}_cfg{i+1}_e{config['epochs']}_img{config['imgsz']}"
        
        # Start an MLflow Run
        with mlflow.start_run(run_name=run_name) as run:
            
            # 1. Log Parameters
            params_to_log = config.copy()
            params_to_log.update({
                "model_type": MODEL_TYPE,
                "data_yaml": data_yaml_path,
                "device": str(device)
            })
            mlflow.log_params(params_to_log)
            
            # 2. Log Dataset Configuration (Versioning)
            mlflow.log_artifact(data_yaml_path, artifact_path="dataset_config")

            # Log the dataset used for this run (populates the 'Datasets' tab in UI)
            ds_info = pd.DataFrame([{"dataset_name": "VisDrone", "yaml_path": os.path.abspath(data_yaml_path)}])
            dataset = mlflow.data.from_pandas(ds_info, name="VisDrone")
            mlflow.log_input(dataset, context="training")

            logger.info(f'_____________________\nRunning Config {i+1}: {config}\n____________________\n\n\n')
            
            model = YOLO(f'./{MODEL_TYPE}.pt')

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
                    single_cls=True,
                    project="runs/train",
                    name=run_name,
                    **config
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
                        # Ensure model is on CPU to avoid pickling issues with GPU tensors
                        best_model.model.to("cpu")

                        # 1. Log the model (Upload artifacts)
                        artifact_path = "model"
                        
                        # Manual Workaround: Save locally -> Upload artifacts -> Register
                        # This bypasses the '404' error caused by log_model() on older servers
                        with tempfile.TemporaryDirectory() as tmp_dir:
                            local_model_path = os.path.join(tmp_dir, "model_build")
                            mlflow.pytorch.save_model(
                                pytorch_model=clean_YOLO_model(best_model),
                                path=local_model_path,
                                pip_requirements=["ultralytics"]
                            )
                            mlflow.log_artifacts(local_model_path, artifact_path=artifact_path)

                        # 2. Register the model using the URI
                        model_uri = f"runs:/{run.info.run_id}/{artifact_path}"
                        reg_model = mlflow.register_model(model_uri, "YOLO_ParkMan_visdrone")

                        # Add description to the registered model version for easier identification in UI
                        client = mlflow.MlflowClient()
                        description = (
                            f"Run ID: {run.info.run_id}\n"
                            f"Config: {config}\n"
                            f"mAP50: {metrics.get('metrics/mAP50_B', 'N/A')}"
                        )
                        client.update_model_version(
                            name="YOLO_ParkMan_visdrone",
                            version=reg_model.version,
                            description=description
                        )
                    except Exception as e:
                        logger.error(f"Failed to register model: {e}", exc_info=True)
                
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
