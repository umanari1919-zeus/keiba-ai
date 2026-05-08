"""
mlflow_register.py — MLflow 実験トラッキング & モデルレジストリ
==============================================================

使い方:
  # model_train_03.py から自動呼び出し（train_model() 終了時）
  python mlflow_register.py D:\\keiba_ai\\model_v8.pkl

  # 手動でメトリクスを確認
  python mlflow_register.py --list

  # MLflow UI 起動
  mlflow ui --backend-store-uri file:///D:/keiba_ai/mlflow_tracking
"""

from __future__ import annotations

import json
import os
import pickle
import sys
from datetime import datetime
from pathlib import Path

TRACKING_URI = os.getenv(
    "MLFLOW_TRACKING_URI",
    f"file:///{Path(os.getenv('KEIBA_BASE', 'D:/keiba_ai')).as_posix()}/mlflow_tracking",
)
EXPERIMENT_NAME = "umanari-ensemble"
MODEL_NAME = "umanari-model"


def _get_git_hash() -> str:
    try:
        import subprocess
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
            cwd=str(Path(__file__).parent),
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def register_model(model_path: str) -> dict:
    """model_v8.pkl を MLflow に登録し、メタデータ JSON も保存する。"""
    import mlflow

    model_path = Path(model_path)
    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")

    with open(model_path, "rb") as f:
        model_data = pickle.load(f)

    metrics = model_data.get("metrics", {})
    features = model_data.get("features", [])
    weights = model_data.get("ensemble_weights", [0.5, 0.3, 0.2])

    mlflow.set_tracking_uri(TRACKING_URI)
    mlflow.set_experiment(EXPERIMENT_NAME)

    git_hash = _get_git_hash()
    run_name = f"v8_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    with mlflow.start_run(run_name=run_name) as run:
        mlflow.log_params({
            "model_version": "v8",
            "n_features": len(features),
            "lgb_weight": weights[0],
            "xgb_weight": weights[1],
            "cb_weight": weights[2] if len(weights) > 2 else 0.0,
            "git_hash": git_hash,
        })

        mlflow.log_metrics({
            "lgb_acc": metrics.get("lgb_acc", 0),
            "xgb_acc": metrics.get("xgb_acc", 0),
            "ensemble_acc": metrics.get("ensemble_acc", 0),
            "ensemble_logloss": metrics.get("ensemble_logloss", 0),
            "val_acc": metrics.get("val_acc", 0),
            "val_logloss": metrics.get("val_logloss", 0),
        })
        if metrics.get("cb_acc") is not None:
            mlflow.log_metric("cb_acc", metrics["cb_acc"])

        mlflow.log_artifact(str(model_path))

        features_path = model_path.parent / "model_features.json"
        features_path.write_text(
            json.dumps(features, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        mlflow.log_artifact(str(features_path))

        run_id = run.info.run_id

    meta = {
        "model_version": "v8",
        "run_id": run_id,
        "run_name": run_name,
        "git_hash": git_hash,
        "n_features": len(features),
        "ensemble_weights": weights,
        "metrics": metrics,
        "features": features,
        "registered_at": datetime.now().isoformat(timespec="seconds"),
        "tracking_uri": TRACKING_URI,
    }

    meta_path = model_path.with_suffix(".meta.json")
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"[MLflow] Registered: run_id={run_id}")
    print(f"[MLflow] Metadata:   {meta_path}")
    return meta


def list_runs(n: int = 10) -> None:
    """最新 N 件のランを表示する。"""
    import mlflow

    mlflow.set_tracking_uri(TRACKING_URI)
    try:
        mlflow.set_experiment(EXPERIMENT_NAME)
    except Exception:
        print("No experiment found. Register a model first.")
        return

    runs = mlflow.search_runs(max_results=n, order_by=["start_time DESC"])
    if runs.empty:
        print("No runs found.")
        return

    cols = ["run_id", "start_time", "metrics.ensemble_acc", "metrics.ensemble_logloss", "params.git_hash"]
    available = [c for c in cols if c in runs.columns]
    print(runs[available].to_string(index=False))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--list":
        list_runs()
    elif len(sys.argv) > 1:
        register_model(sys.argv[1])
    else:
        default_path = Path(os.getenv("KEIBA_BASE", "D:/keiba_ai")) / "model_v8.pkl"
        if default_path.exists():
            register_model(str(default_path))
        else:
            print(f"Usage: python mlflow_register.py <model_path>")
            print(f"       python mlflow_register.py --list")
