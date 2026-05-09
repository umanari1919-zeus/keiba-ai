"""
直接実行互換用の package shim。

`python pipeline/foo.py` では sys.path[0] が pipeline/ になるため、
`from pipeline.config import ...` が親ディレクトリを見つけられない。
この shim は、その場合だけ実体の pipeline/ を package path として公開する。
"""

from __future__ import annotations

import pathlib

__path__ = [str(pathlib.Path(__file__).resolve().parent.parent)]
