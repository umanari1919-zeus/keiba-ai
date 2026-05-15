"""mlflow_register.py のユニットテスト。"""

import json
import pickle

import pytest
from unittest.mock import MagicMock, patch

mlflow = pytest.importorskip("mlflow")


@pytest.mark.unit
class TestMlflowRegister:
    def test_register_model_creates_meta_json(self, tmp_path, monkeypatch):
        model_data = {
            "features": ["f1", "f2", "f3"],
            "ensemble_weights": [0.5, 0.3, 0.2],
            "metrics": {
                "lgb_acc": 0.65,
                "xgb_acc": 0.63,
                "cb_acc": 0.61,
                "ensemble_acc": 0.67,
                "ensemble_logloss": 0.55,
                "val_acc": 0.64,
                "val_logloss": 0.58,
            },
        }
        pkl_path = tmp_path / "model_v8.pkl"
        with open(pkl_path, "wb") as f:
            pickle.dump(model_data, f)

        monkeypatch.setenv("MLFLOW_TRACKING_URI", f"file:///{tmp_path.as_posix()}/mlflow")

        from mlflow_register import register_model
        meta = register_model(str(pkl_path))

        assert meta["model_version"] == "v8"
        assert meta["n_features"] == 3
        assert meta["ensemble_weights"] == [0.5, 0.3, 0.2]
        assert meta["metrics"]["ensemble_acc"] == 0.67
        assert "run_id" in meta

        meta_file = pkl_path.with_suffix(".meta.json")
        assert meta_file.exists()
        saved = json.loads(meta_file.read_text(encoding="utf-8"))
        assert saved["run_id"] == meta["run_id"]

    def test_register_model_file_not_found(self):
        from mlflow_register import register_model
        with pytest.raises(FileNotFoundError):
            register_model("/nonexistent/model.pkl")

    def test_list_runs_no_experiment(self, tmp_path, monkeypatch, capsys):
        empty_uri = f"file:///{(tmp_path / 'mlflow_isolated').as_posix()}"

        import mlflow_register
        monkeypatch.setattr(mlflow_register, "TRACKING_URI", empty_uri)
        monkeypatch.setattr(mlflow_register, "EXPERIMENT_NAME", "nonexistent-exp")
        mlflow.set_tracking_uri(empty_uri)

        mlflow_register.list_runs()

        captured = capsys.readouterr()
        assert "No experiment" in captured.out or "No runs" in captured.out
