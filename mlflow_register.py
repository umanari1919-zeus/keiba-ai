# mlflow_register.py
import sys, os, mlflow, shutil
from datetime import datetime

model_file = sys.argv[1]
tracking_uri = "file:///D:/mlflow_tracking"
mlflow.set_tracking_uri(tracking_uri)

model_name = os.path.basename(model_file)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

# MLflowのモデルディレクトリにコピー
models_dir = "D:/mlflow_tracking/models"
os.makedirs(models_dir, exist_ok=True)
dest = os.path.join(models_dir, f"{model_name}_{timestamp}.pkl")
shutil.copy(model_file, dest)

print(f"Model artifact archived: {dest}")
print(f"MLflow tracking URI: {tracking_uri}")
print("Use: mlflow models serve -m file://{}/models --port 5000".format(models_dir))
