# mlflow_register.py
import sys, os, mlflow
model_file = sys.argv[1]
mlflow.set_tracking_uri("file:///D:/mlflow_tracking")
with mlflow.start_run() as run:
    mlflow.log_artifact(model_file, artifact_path="models")
    artifact_path = f"runs:/{run.info.run_id}/models/{os.path.basename(model_file)}"
    mlflow.register_model(artifact_path, "keiba_model_registry")
print("Registered model", model_file)
