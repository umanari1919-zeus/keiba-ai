"""
Neural Network (PyTorch) + Stacking メタ学習
- MLP with BatchNorm + Dropout
- Stacking: LGB/XGB/CB/NN → LightGBM メタ学習器
- アンサンブル重み動的最適化
"""
import pandas as pd
import numpy as np
import pickle
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.metrics import accuracy_score
from scipy.optimize import minimize
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
import lightgbm as lgb
from datetime import datetime

MODEL_FILE    = "D:\\keiba_ai\\model_v8.pkl"
STACKED_FILE  = "D:\\keiba_ai\\model_stacked.pkl"
NN_FILE       = "D:\\keiba_ai\\model_nn.pth"


# ──────────────────────────────────────────────
# PyTorch MLP
# ──────────────────────────────────────────────

class RaceMLP(nn.Module):
    def __init__(self, input_dim: int, num_classes: int,
                 hidden_dims=(512, 256, 128), dropout=0.3):
        super().__init__()
        layers = []
        prev = input_dim
        for h in hidden_dims:
            layers += [nn.Linear(prev, h), nn.BatchNorm1d(h),
                       nn.ReLU(), nn.Dropout(dropout)]
            prev = h
        layers.append(nn.Linear(prev, num_classes))
        self.net = nn.Sequential(*layers)

    def forward(self, x):
        return self.net(x)


def train_nn(X_train, y_train, X_val, y_val, num_classes,
             epochs=30, batch_size=1024, lr=1e-3, device='cpu'):
    scaler   = StandardScaler()
    X_tr_sc  = scaler.fit_transform(X_train.astype(np.float32))
    X_val_sc = scaler.transform(X_val.astype(np.float32))

    Xtr = torch.tensor(X_tr_sc,  dtype=torch.float32)
    ytr = torch.tensor(y_train,  dtype=torch.long)
    Xvl = torch.tensor(X_val_sc, dtype=torch.float32)
    yvl = torch.tensor(y_val,    dtype=torch.long)

    ds     = TensorDataset(Xtr, ytr)
    loader = DataLoader(ds, batch_size=batch_size, shuffle=True)

    model = RaceMLP(X_tr_sc.shape[1], num_classes).to(device)
    opt   = optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    sched = optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
    crit  = nn.CrossEntropyLoss()

    best_acc, best_state = 0, None
    for epoch in range(epochs):
        model.train()
        for Xb, yb in loader:
            Xb, yb = Xb.to(device), yb.to(device)
            loss   = crit(model(Xb), yb)
            opt.zero_grad(); loss.backward(); opt.step()
        sched.step()

        model.eval()
        with torch.no_grad():
            preds = model(Xvl.to(device)).argmax(1).cpu().numpy()
        acc = accuracy_score(yvl.numpy(), preds)
        if acc > best_acc:
            best_acc = acc
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

        if (epoch + 1) % 10 == 0:
            print(f"    Epoch {epoch+1:3d}/{epochs}  val_acc={acc:.4f}")

    model.load_state_dict(best_state)
    print(f"  🧠 NN最高精度: {best_acc:.4f}")
    return model, scaler


def nn_predict_proba(model, scaler, X, device='cpu', batch_size=4096):
    model.eval()
    Xs  = scaler.transform(X.astype(np.float32))
    Xt  = torch.tensor(Xs, dtype=torch.float32)
    out = []
    with torch.no_grad():
        for i in range(0, len(Xt), batch_size):
            logits = model(Xt[i:i+batch_size].to(device))
            out.append(torch.softmax(logits, dim=1).cpu().numpy())
    return np.vstack(out)


# ──────────────────────────────────────────────
# アンサンブル重み動的最適化
# ──────────────────────────────────────────────

def optimize_ensemble_weights(probas_list, y_true):
    """
    各モデルの予測確率リストを受け取り、アンサンブル精度を最大化する重みを返す。
    """
    n = len(probas_list)

    def neg_acc(w):
        w = np.array(w)
        w = np.abs(w) / np.abs(w).sum()
        ensemble = sum(wi * p for wi, p in zip(w, probas_list))
        preds = ensemble.argmax(axis=1)
        return -accuracy_score(y_true, preds)

    w0     = np.ones(n) / n
    bounds = [(0, 1)] * n
    result = minimize(neg_acc, w0, method='SLSQP',
                      bounds=bounds,
                      constraints={'type': 'eq', 'fun': lambda w: np.sum(np.abs(w)) - 1})
    weights = np.abs(result.x) / np.abs(result.x).sum()
    return weights


# ──────────────────────────────────────────────
# Stacking メタ学習
# ──────────────────────────────────────────────

def build_stacking_model(X, y, base_models, le, n_splits=5):
    """
    Stacking: base_models の OOF 予測を特徴量にして LightGBM メタ学習。
    """
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    oof_probas = []

    for name, model in base_models.items():
        oof = np.zeros((len(X), len(le.classes_)))
        for fold, (tr_idx, vl_idx) in enumerate(skf.split(X, y)):
            Xtr, Xvl = X.iloc[tr_idx], X.iloc[vl_idx]
            ytr       = y.iloc[tr_idx]
            model.fit(Xtr, ytr)
            oof[vl_idx] = model.predict_proba(Xvl)
        oof_probas.append(oof)
        print(f"    {name} OOF acc: {accuracy_score(y, oof.argmax(1)):.4f}")

    # スタッキング特徴量
    meta_X = np.hstack(oof_probas)

    # メタ学習器（LightGBM）
    meta_lgb = lgb.LGBMClassifier(n_estimators=200, learning_rate=0.05,
                                   num_leaves=31, random_state=42, verbose=-1)
    meta_lgb.fit(meta_X, y)
    stacking_acc = accuracy_score(y, meta_lgb.predict(meta_X))
    print(f"  📈 Stacking訓練精度: {stacking_acc:.4f}")
    return meta_lgb


# ──────────────────────────────────────────────
# メイン実行
# ──────────────────────────────────────────────

def train_nn_stacking():
    print("\n" + "="*55)
    print("🧠 Neural Network + Stacking 学習")
    print("="*55)

    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"  Device: {device}")

    # 既存モデルを読み込み
    with open(MODEL_FILE, 'rb') as f:
        saved = pickle.load(f)
    lgb_model = saved['lgb_model']
    xgb_model = saved['xgb_model']
    cb_model  = saved['cb_model']
    le        = saved['le']
    features  = saved['features']

    df = pd.read_csv("D:\\keiba_ai\\keiba_data_features.csv",
                     encoding="utf-8-sig", low_memory=False)
    df = df.fillna(0)
    feats = [f for f in features if f in df.columns]

    X = df[feats].values.astype(np.float32)
    y_raw = df['kakutei_chakujun'].values
    le_nn = LabelEncoder()
    y = le_nn.fit_transform(y_raw)

    # 80:20 分割
    split_idx = int(len(X) * 0.8)
    X_tr, X_vl = X[:split_idx], X[split_idx:]
    y_tr, y_vl = y[:split_idx], y[split_idx:]

    # NN 学習
    print("\n  🔍 Neural Network 学習中...")
    nn_model, nn_scaler = train_nn(X_tr, y_tr, X_vl, y_vl,
                                   num_classes=len(le_nn.classes_),
                                   epochs=30, device=device)

    # NN 評価
    nn_proba = nn_predict_proba(nn_model, nn_scaler, X_vl, device)
    nn_acc   = accuracy_score(y_vl, nn_proba.argmax(1))
    print(f"  🎯 NN テスト精度: {nn_acc:.4f}")

    # 既存モデルの予測確率（valセットのみ）
    X_vl_df = pd.DataFrame(X_vl, columns=feats)
    lgb_proba = lgb_model.predict_proba(X_vl_df)
    xgb_proba = xgb_model.predict_proba(X_vl_df)
    cb_proba  = cb_model.predict_proba(X_vl_df)

    # 動的重み最適化
    print("\n  ⚖️ アンサンブル重み動的最適化中...")
    probas_list = [lgb_proba, xgb_proba, cb_proba, nn_proba]
    weights = optimize_ensemble_weights(probas_list, y_vl)
    print(f"  最適重み: LGB={weights[0]:.3f} XGB={weights[1]:.3f} "
          f"CB={weights[2]:.3f} NN={weights[3]:.3f}")

    ensemble_proba = sum(w * p for w, p in zip(weights, probas_list))
    ensemble_acc   = accuracy_score(y_vl, ensemble_proba.argmax(1))
    print(f"  🎯 最適化アンサンブル精度: {ensemble_acc:.4f}")

    # モデルを保存
    torch.save({'model_state': nn_model.state_dict(),
                'input_dim':   X_tr.shape[1],
                'num_classes': len(le_nn.classes_),
                'scaler':      nn_scaler}, NN_FILE)

    # 既存モデルにNN情報を追加保存
    saved['nn_weights_path'] = NN_FILE
    saved['ensemble_weights'] = weights.tolist()
    saved['le_nn'] = le_nn
    with open(MODEL_FILE, 'wb') as f:
        pickle.dump(saved, f)

    print(f"\n  💾 NN モデル保存: {NN_FILE}")
    print(f"  💾 最適重み保存: model_v8.pkl")

    return nn_model, nn_scaler, weights


if __name__ == "__main__":
    train_nn_stacking()
