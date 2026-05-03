import numpy as np


def load_ensemble_weights(saved: dict, n_models: int = 3, default=None) -> list[float]:
    """
    model_v8.pkl からアンサンブル重みを読み取り、件数・合計1に正規化して返す。
    NN込み4重みなどが保存されていても先頭 n_models を使用する。
    """
    if default is None:
        default = [0.5, 0.3, 0.2]

    raw = saved.get("ensemble_weights", default)
    try:
        w = np.asarray(raw, dtype=float).flatten()
    except Exception:
        w = np.asarray(default, dtype=float)

    if w.size < n_models:
        fallback = np.asarray(default, dtype=float)
        if fallback.size < n_models:
            fallback = np.pad(fallback, (0, n_models - fallback.size), constant_values=0.0)
        w = fallback[:n_models]
    else:
        w = w[:n_models]

    w = np.clip(w, 0.0, None)
    s = float(w.sum())
    if s <= 0:
        w = np.asarray(default[:n_models], dtype=float)
        s = float(w.sum())
    if s <= 0:
        w = np.full(n_models, 1.0 / n_models, dtype=float)
    else:
        w = w / s
    return w.tolist()
