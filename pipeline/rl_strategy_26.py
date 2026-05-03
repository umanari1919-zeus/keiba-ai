"""
強化学習による馬券戦略の最適化
- Gymnasium カスタム環境
- PPO エージェント（stable-baselines3）
- 学習済み戦略を predict_04.py のフィルタとして使用
"""
import numpy as np
import pandas as pd
import json
import os
import pickle
from datetime import datetime

try:
    import gymnasium as gym
    from gymnasium import spaces
    from stable_baselines3 import PPO
    from stable_baselines3.common.env_checker import check_env
    RL_AVAILABLE = True
except ImportError:
    RL_AVAILABLE = False

DATA_DIR  = "D:\\keiba_ai\\data"
RL_MODEL  = "D:\\keiba_ai\\rl_strategy.zip"


# ──────────────────────────────────────────────
# カスタム競馬環境
# ──────────────────────────────────────────────

if RL_AVAILABLE:
    class KeibaEnv(gym.Env):
        """
        状態: [win_prob, odds, ev, bankroll_ratio, drawdown, is_high_odds]
        行動: 0=パス, 1=ベット_小(2%), 2=ベット_中(3.5%), 3=ベット_大(5%)
        報酬: 的中なら +odds*bet/bankroll, 外れなら -bet/bankroll
        """
        metadata = {'render_modes': []}

        def __init__(self, data: pd.DataFrame, bankroll=100000):
            super().__init__()
            self.data      = data.reset_index(drop=True)
            self.bankroll0 = bankroll
            self.n_races   = len(data)

            self.observation_space = spaces.Box(
                low=-10, high=10, shape=(6,), dtype=np.float32
            )
            self.action_space = spaces.Discrete(4)  # 0:パス, 1:小, 2:中, 3:大

        def reset(self, seed=None, options=None):
            super().reset(seed=seed)
            self.idx      = 0
            self.bankroll = self.bankroll0
            self.peak     = self.bankroll0
            return self._obs(), {}

        def _obs(self):
            if self.idx >= self.n_races:
                return np.zeros(6, dtype=np.float32)
            row = self.data.iloc[self.idx]
            win_prob = float(row.get('win_prob', 0.1))
            odds     = float(row.get('odds', 5.0))
            ev       = win_prob * odds - 1
            br_ratio = self.bankroll / self.bankroll0
            dd       = max(0, (self.peak - self.bankroll) / self.peak)
            hi_odds  = float(odds >= 10.0)
            return np.array([win_prob, min(odds/100, 1), ev, br_ratio, dd, hi_odds],
                             dtype=np.float32)

        def step(self, action):
            BET_FRACS = [0.0, 0.02, 0.035, 0.05]
            row   = self.data.iloc[self.idx]
            odds  = float(row.get('odds', 5.0))
            hit   = int(row.get('hit', 0))
            frac  = BET_FRACS[action]
            bet   = self.bankroll * frac

            if action == 0:
                reward = 0.0
            elif hit:
                gain   = bet * (odds - 1)
                self.bankroll += gain
                reward = gain / self.bankroll0
            else:
                self.bankroll -= bet
                reward = -bet / self.bankroll0

            self.bankroll = max(0, self.bankroll)
            if self.bankroll > self.peak:
                self.peak = self.bankroll

            # 破産ペナルティ
            if self.bankroll < self.bankroll0 * 0.3:
                reward -= 1.0

            self.idx += 1
            done = self.idx >= self.n_races or self.bankroll <= 0
            return self._obs(), reward, done, False, {}

        def render(self):
            pass


# ──────────────────────────────────────────────
# RL 学習
# ──────────────────────────────────────────────

def train_rl_strategy(n_timesteps=200_000):
    if not RL_AVAILABLE:
        print("  ⚠️ gymnasium / stable-baselines3 が未インストール")
        return None

    print("\n" + "="*55)
    print("🤖 強化学習 馬券戦略最適化 (PPO)")
    print("="*55)

    # 学習データ（simulation_2025.csv から）
    try:
        sim_df = pd.read_csv("D:\\keiba_ai\\simulation_2025.csv",
                             encoding="utf-8-sig", on_bad_lines="skip")
        sim_df['win_prob'] = sim_df.get('win_prob', 0.1)
        if 'odds' not in sim_df.columns and 'tansho_odds' in sim_df.columns:
            sim_df['odds'] = sim_df['tansho_odds'] / 10
    except Exception as e:
        print(f"  ⚠️ データ読み込みエラー: {e}")
        return None

    env = KeibaEnv(sim_df)
    try:
        check_env(env, warn=True)
    except Exception:
        pass

    model = PPO('MlpPolicy', env,
                learning_rate=3e-4,
                n_steps=2048,
                batch_size=64,
                n_epochs=10,
                gamma=0.99,
                verbose=0)

    print(f"  学習開始: {n_timesteps:,}ステップ...")
    model.learn(total_timesteps=n_timesteps)

    model.save(RL_MODEL)
    print(f"  💾 RLモデル保存: {RL_MODEL}")

    # 評価
    obs, _ = env.reset()
    total_reward = 0
    for _ in range(len(sim_df)):
        action, _ = model.predict(obs, deterministic=True)
        obs, reward, done, _, _ = env.step(action)
        total_reward += reward
        if done:
            break

    roi = env.bankroll / env.bankroll0
    print(f"  📊 RL評価 最終回収率: {roi*100:.1f}%")
    return model


# ──────────────────────────────────────────────
# RL 推論（predict_04.py での使用）
# ──────────────────────────────────────────────

def rl_betting_decision(win_prob: float, odds: float,
                         bankroll: float, bankroll0: float,
                         peak: float) -> str:
    """
    学習済みRLモデルで bet/pass を判断する。
    Returns: 'small'|'medium'|'large'|'pass'
    """
    if not RL_AVAILABLE or not os.path.exists(RL_MODEL + '.zip'):
        # フォールバック: EVベースの判断
        ev = win_prob * odds - 1
        if ev < 0.05 or odds < 10:
            return 'pass'
        return 'medium'

    try:
        model = PPO.load(RL_MODEL)
        dd    = max(0, (peak - bankroll) / peak) if peak > 0 else 0
        obs   = np.array([win_prob, min(odds/100, 1),
                           win_prob*odds-1, bankroll/bankroll0,
                           dd, float(odds >= 10)], dtype=np.float32)
        action, _ = model.predict(obs, deterministic=True)
        return ['pass', 'small', 'medium', 'large'][int(action)]
    except Exception:
        return 'medium'


if __name__ == "__main__":
    model = train_rl_strategy(n_timesteps=100_000)
    if model:
        print("\n  テスト推論:")
        for wp, od in [(0.05, 50.0), (0.10, 20.0), (0.30, 3.0)]:
            decision = rl_betting_decision(wp, od, 100000, 100000, 100000)
            print(f"    勝率{wp*100:.0f}% オッズ{od:.1f}x → {decision}")
