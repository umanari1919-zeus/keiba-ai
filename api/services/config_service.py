"""
パイプライン設定管理サービス

pipeline/config.py のパラメータを読み込み・更新し、
Settings API で動的設定変更を実現する。
"""
import re
import importlib
from pathlib import Path
from typing import Dict, Any
from datetime import datetime


class ConfigService:
    """設定パラメータの読み込み・書き込み管理"""

    _config_path = Path("pipeline/config.py")
    _defaults = {
        "EV_THRESHOLD": 0.15,
        "KELLY_FRACTION": 0.10,
        "MIN_ODDS": 10.0,
        "MIN_ODDS_BACKTEST": 10.0,
    }

    @classmethod
    def get_parameters(cls) -> Dict[str, Any]:
        """
        現在の設定パラメータを読み込む

        Returns:
            パラメータ辞書 + updated_at タイムスタンプ
        """
        try:
            import pipeline.config as cfg
            return {
                "EV_THRESHOLD": getattr(cfg, "EV_THRESHOLD", cls._defaults["EV_THRESHOLD"]),
                "KELLY_FRACTION": getattr(cfg, "KELLY_FRACTION", cls._defaults["KELLY_FRACTION"]),
                "MIN_ODDS": getattr(cfg, "MIN_ODDS", cls._defaults["MIN_ODDS"]),
                "MIN_ODDS_BACKTEST": getattr(cfg, "MIN_ODDS_BACKTEST", cls._defaults["MIN_ODDS_BACKTEST"]),
                "updated_at": datetime.now(),
            }
        except ImportError:
            return {**cls._defaults, "updated_at": datetime.now()}

    @classmethod
    def set_parameter(cls, key: str, value: float) -> None:
        """
        設定パラメータを更新

        Args:
            key: パラメータキー（EV_THRESHOLD など）
            value: 新規値

        Raises:
            ValueError: 無効なキー・値の場合
            IOError: ファイル書き込み失敗の場合
        """
        # キー検証
        if key not in cls._defaults:
            raise ValueError(f"Invalid parameter key: {key}. Must be one of {list(cls._defaults.keys())}")

        # 値の型・範囲検証
        if not isinstance(value, (int, float)):
            raise ValueError(f"Parameter value must be numeric, got {type(value).__name__}")

        if value <= 0:
            raise ValueError(f"Parameter value must be positive, got {value}")

        # config.py ファイル読み込み
        try:
            content = cls._config_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise IOError(f"Config file not found: {cls._config_path}")

        # 正規表現で置換（コメント後ろの値のみ変更）
        pattern = rf"^({key}\s*=\s*)[\d.]+"
        new_content = re.sub(
            pattern,
            rf"\g<1>{value}",
            content,
            flags=re.MULTILINE,
        )

        # 置換が発生したか確認
        if new_content == content:
            raise ValueError(f"Parameter {key} not found in config.py or already has value {value}")

        # ファイル書き込み
        try:
            cls._config_path.write_text(new_content, encoding="utf-8")
        except IOError as e:
            raise IOError(f"Failed to write config file: {e}")

        # Python モジュール再読み込み（メモリ上の設定を更新）
        try:
            import pipeline.config
            importlib.reload(pipeline.config)
        except Exception as e:
            raise RuntimeError(f"Failed to reload config module: {e}")

    @classmethod
    def reset_parameters(cls) -> None:
        """
        すべてのパラメータをデフォルト値にリセット

        Raises:
            IOError: ファイル書き込み失敗の場合
        """
        for key, default_value in cls._defaults.items():
            try:
                cls.set_parameter(key, default_value)
            except ValueError:
                # キーが存在しない場合はスキップ
                pass

    @classmethod
    def validate_parameters(cls, params: Dict[str, float]) -> bool:
        """
        パラメータ値の妥当性を検証

        Args:
            params: パラメータ辞書

        Returns:
            すべて妥当な場合 True
        """
        for key, value in params.items():
            if key not in cls._defaults:
                return False
            if not isinstance(value, (int, float)) or value <= 0:
                return False
        return True
