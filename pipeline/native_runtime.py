"""
Native runtime helpers for ML libraries.

Some Linux environments do not ship libgomp by default. LightGBM, XGBoost,
and CatBoost can require it at import time, so we preload a user-provided copy
when available.
"""

from __future__ import annotations

import ctypes
import os
import pathlib
from functools import lru_cache


@lru_cache(maxsize=1)
def ensure_native_runtime() -> list[str]:
    loaded: list[str] = []
    candidates = []
    env_dir = os.getenv("KEIBA_NATIVE_LIB_DIR")
    if env_dir:
        candidates.append(pathlib.Path(env_dir))
    candidates.append(
        pathlib.Path.home()
        / ".local"
        / "share"
        / "keiba_ai"
        / "syslibs"
        / "usr"
        / "lib"
        / "x86_64-linux-gnu"
    )

    for lib_dir in candidates:
        libgomp = lib_dir / "libgomp.so.1"
        if not libgomp.exists():
            continue
        ctypes.CDLL(str(libgomp), mode=ctypes.RTLD_GLOBAL)
        loaded.append(str(libgomp))
        break
    return loaded
