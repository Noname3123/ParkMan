import tempfile
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

# CHANGE: MLflow "best model" retrieval imports
from mlflow.tracking import MlflowClient
import mlflow


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

data_yaml_path = './VisDrone/data-visdrone.yaml'

param_grid = {
    'epochs': [10],
    'imgsz': [640],
}

MODEL_TYPE = 'yolo11m'

#.---------------------
#helper functions
#.---------------------

from mlflow.tracking import MlflowClient
import mlflow

def _safe_float(x):
    try:
        return float(x)
    except Exception:
        return None


def get_best_model_info_from_registry(
    model_name: str,
    metric_key: str = "metrics/mAP50_B",
    weights_artifact_path: str = "weights/best.pt",
    tracking_uri: str = None,
) -> dict | None:
    """
    Returns dict with info about best-ever model in registry:
      {
        "score": float,
        "run_id": str,
        "version": str/int,
        "weights_path": str (downloaded local path or None if download fails)
      }

    # CHANGE:
      - metric_key: switch to "model_fitness" if desired
      - weights_artifact_path: adjust if your artifact path differs
    """
    if tracking_uri:
        mlflow.set_tracking_uri(tracking_uri)

    client = MlflowClient()

    try:
        versions = client.search_model_versions(f"name='{model_name}'")
    except Exception as e:
        print(f"[MLflow] Could not search model versions for '{model_name}': {e}")
        return None

    if not versions:
        print(f"[MLflow] No registered model versions found for '{model_name}'.")
        return None

    best = {"score": None, "run_id": None, "version": None}

    for v in versions:
        run_id = getattr(v, "run_id", None)
        ver = getattr(v, "version", None)
        if not run_id:
            continue

        try:
            run = client.get_run(run_id)
        except Exception as e:
            print(f"[MLflow] Could not get run '{run_id}' (model v{ver}): {e}")
            continue

        score = run.data.metrics.get(metric_key)
        score_f = _safe_float(score)
        if score_f is None:
            continue

        if best["score"] is None or score_f > best["score"]:
            best = {"score": score_f, "run_id": run_id, "version": ver}

    if best["run_id"] is None:
        print(f"[MLflow] No runs in registry had metric '{metric_key}'.")
        return None

    print(f"[MLflow] Best model so far: name={model_name} version={best['version']} "
          f"run_id={best['run_id']} {metric_key}={best['score']}")

    # Download best weights (optional but useful for init weights)
    weights_path = None
    try:
        weights_path = mlflow.artifacts.download_artifacts(
            run_id=best["run_id"],
            artifact_path=weights_artifact_path
        )
        print(f"[MLflow] Downloaded best weights to: {weights_path}")
    except Exception as e:
        print(f"[MLflow] Could not download best weights artifact '{weights_artifact_path}': {e}")

    return {
        "score": best["score"],
        "run_id": best["run_id"],
        "version": best["version"],
        "weights_path": weights_path
    }

def set_best_alias_if_improved(
    model_name: str,
    new_version: str | int,
    new_score: float,
    old_best_score: float | None,
    alias_name: str = "best_stability",
    metric_key: str = "metrics/mAP50_B",
    tracking_uri: str = None,
) -> None:
    """
    If new_score > old_best_score, set MLflow alias to point to new_version.

    Preferred:
      MlflowClient().set_registered_model_alias(model_name, alias_name, new_version)

    Fallback:
      set model version tag (works even if aliases aren't supported)
    """
    if tracking_uri:
        mlflow.set_tracking_uri(tracking_uri)

    client = MlflowClient()

    if old_best_score is not None and new_score <= old_best_score:
        print(f"[MLflow] New model NOT better: new {metric_key}={new_score} <= best {old_best_score}. "
              f"Alias '{alias_name}' unchanged.")
        return

    print(f"[MLflow] New model IS better (or no previous best). Setting alias '{alias_name}' "
          f"to version={new_version} ({metric_key}={new_score}).")

    # Try aliases (newer MLflow)
    try:
        client.set_registered_model_alias(model_name, alias_name, str(new_version))
        print(f"[MLflow] Alias '{alias_name}' set to {model_name} v{new_version}.")
        return
    except Exception as e:
        print(f"[MLflow] Alias API not available or failed: {e}. Falling back to model version tag.")

    # Fallback: tag the model version as best
    try:
        # CHANGE: tag name if you want a different convention
        client.set_model_version_tag(model_name, str(new_version), "alias", alias_name)
        client.set_model_version_tag(model_name, str(new_version), "best_metric_key", metric_key)
        client.set_model_version_tag(model_name, str(new_version), "best_metric_value", str(new_score))
        print(f"[MLflow] Set model version tags on {model_name} v{new_version} as best='{alias_name}'.")
    except Exception as e:
        print(f"[MLflow] Failed to set model version tags: {e}")



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
    for epochs, imgsz in product(param_grid['epochs'], param_grid['imgsz']):
        
        # Define a run name for MLflow
        run_name = f"{MODEL_TYPE}_e{epochs}_img{imgsz}"
        
        # Start an MLflow Run
        with mlflow.start_run(run_name=run_name) as run:
            
            # 1. Log Parameters
            mlflow.log_params({
                "epochs": epochs,
                "imgsz": imgsz,
                "batch_size": 4,
                "model_type": MODEL_TYPE,
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
            
            # ============================================================
            # Choose training starting weights:
            # - Prefer BEST EVER weights from MLflow registry (by metrics/mAP50_B)
            # - Fallback to base pretrained MODEL_TYPE weights if MLflow not available
            # ============================================================

            # CHANGE: MLflow tracking URI (in compose: http://mlflow_server:5000)
            MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow_server:5000")  # CHANGE

            # CHANGE: Registry model name (must match what you register in MLflow)
            MLFLOW_MODEL_NAME = os.getenv("MLFLOW_MODEL_NAME", "YOLO_ParkMan_visdrone")  # CHANGE

            # CHANGE: Metric used to select "best ever"
            # Default per your request:
            BEST_METRIC_KEY = "metrics/mAP50_B"  # CHANGE: set to "model_fitness" if you decide to use that instead

            # CHANGE: Artifact path inside the MLflow run where best weights are stored
            BEST_WEIGHTS_ARTIFACT_PATH = "weights/best.pt"  # CHANGE

            best_info = get_best_model_info_from_registry(
                model_name=MLFLOW_MODEL_NAME,
                metric_key=BEST_METRIC_KEY,
                weights_artifact_path=BEST_WEIGHTS_ARTIFACT_PATH,
                tracking_uri=MLFLOW_TRACKING_URI,
            )

            best_score_before = best_info["score"] if best_info else None
            best_weights_path = best_info["weights_path"] if best_info else None

            if best_weights_path:
                print(f"[Training] Using BEST weights from MLflow: {best_weights_path}")
                model = YOLO(best_weights_path)
            else:
                print(f"[Training] MLflow best weights not available. Falling back to base: ./{MODEL_TYPE}.pt")
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
                            f"Epochs: {epochs}, Imgsz: {imgsz}\n"
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
