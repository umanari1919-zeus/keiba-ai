"""
rag_store.py — Vector DB / RAG 基盤
=====================================
類似馬検索と LLM 根拠補強のための埋め込みストア。

優先順位:
  1. chromadb  (pip install chromadb)
  2. faiss     (pip install faiss-cpu)
  3. JSON ファイルベース（フォールバック、常に利用可能）

マニフェスト vector_search_rag の実装:
  inputs:  pedigree_embeddings, feature_embeddings
  purpose: 類似馬検索 / LLM 根拠補強
"""

from __future__ import annotations

import json
import logging
import math
import os
import pathlib
from typing import Any

log = logging.getLogger(__name__)

BASE_DIR   = pathlib.Path(os.getenv("KEIBA_BASE", "D:/keiba_ai"))
STORE_DIR  = BASE_DIR / "data" / "rag_store"
STORE_DIR.mkdir(parents=True, exist_ok=True)

COLLECTION_NAME = "umanari_horses"
EMBED_DIM       = 32   # 軽量ベクトル次元（フォールバック用）


# ================================================================== #
# バックエンド検出
# ================================================================== #

def _detect_backend() -> str:
    try:
        import chromadb  # noqa: F401
        return "chromadb"
    except ImportError:
        pass
    try:
        import faiss  # noqa: F401
        return "faiss"
    except ImportError:
        pass
    return "json"


BACKEND = _detect_backend()
log.debug("RAG backend: %s", BACKEND)


# ================================================================== #
# 埋め込み生成（特徴量ベクトルから軽量埋め込みを生成）
# ================================================================== #

def embed_horse(features: dict) -> list[float]:
    """
    馬の特徴量辞書から固定長埋め込みベクトルを生成する。
    Claude API (text embedding) または 簡易数値ハッシュを使用。
    """
    # 数値特徴量を正規化して固定長ベクトル化
    keys = [
        "win_prob", "place_prob", "expected_return", "uncertainty",
        "odds", "win_rate", "place_rate", "past3_avg_chakujun",
        "nick_index", "futan_juryo", "bataiju", "kyori",
        "sire_win_rate", "sire_roi", "bms_win_rate",
        "debut_score", "shogai_score", "training_speed_zscore",
    ]
    vec = []
    for k in keys:
        v = features.get(k, 0.0)
        try:
            vec.append(float(v))
        except (TypeError, ValueError):
            vec.append(0.0)

    # パディングして EMBED_DIM に揃える
    while len(vec) < EMBED_DIM:
        vec.append(0.0)
    return vec[:EMBED_DIM]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot  = sum(x * y for x, y in zip(a, b))
    na   = math.sqrt(sum(x**2 for x in a))
    nb   = math.sqrt(sum(x**2 for x in b))
    return dot / (na * nb + 1e-9)


# ================================================================== #
# RAGStore クラス
# ================================================================== #

class RAGStore:
    """
    馬の埋め込みを格納・検索する統合インタフェース。
    バックエンド (chromadb / faiss / json) を自動選択。
    """

    def __init__(self, collection: str = COLLECTION_NAME):
        self.collection = collection
        self._backend   = BACKEND
        self._client    = None
        self._json_path = STORE_DIR / f"{collection}.jsonl"
        self._init_backend()

    # ------------------------------------------------------------------ #
    # 初期化
    # ------------------------------------------------------------------ #

    def _init_backend(self) -> None:
        if self._backend == "chromadb":
            try:
                import chromadb
                self._client = chromadb.PersistentClient(path=str(STORE_DIR / "chroma"))
                self._col    = self._client.get_or_create_collection(
                    name=self.collection,
                    metadata={"hnsw:space": "cosine"},
                )
                log.info("RAG: chromadb backend (%s docs)", self._col.count())
            except Exception as exc:
                log.warning("chromadb 初期化失敗→ json fallback: %s", exc)
                self._backend = "json"

        elif self._backend == "faiss":
            try:
                import faiss, numpy as np
                self._faiss_index = faiss.IndexFlatL2(EMBED_DIM)
                self._faiss_meta: list[dict] = []
                # 永続化ファイルから読み込み
                faiss_path = STORE_DIR / f"{self.collection}.faiss"
                meta_path  = STORE_DIR / f"{self.collection}_meta.json"
                if faiss_path.exists():
                    self._faiss_index = faiss.read_index(str(faiss_path))
                    self._faiss_meta  = json.loads(meta_path.read_text(encoding="utf-8"))
                log.info("RAG: faiss backend (%d docs)", len(self._faiss_meta))
            except Exception as exc:
                log.warning("faiss 初期化失敗→ json fallback: %s", exc)
                self._backend = "json"

        if self._backend == "json":
            log.info("RAG: json fallback backend (%s)", self._json_path)

    # ------------------------------------------------------------------ #
    # 追加
    # ------------------------------------------------------------------ #

    def add(self, horse_id: str, features: dict, metadata: dict | None = None) -> None:
        vec = embed_horse(features)
        meta = {**(metadata or {}), "horse_id": horse_id}

        if self._backend == "chromadb":
            self._col.upsert(
                ids=[horse_id],
                embeddings=[vec],
                metadatas=[meta],
            )

        elif self._backend == "faiss":
            import numpy as np
            arr = np.array([vec], dtype=np.float32)
            self._faiss_index.add(arr)
            self._faiss_meta.append({"horse_id": horse_id, **meta})
            self._save_faiss()

        else:  # json
            record = {"horse_id": horse_id, "vector": vec, "meta": meta}
            with open(self._json_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # ------------------------------------------------------------------ #
    # 検索
    # ------------------------------------------------------------------ #

    def search(self, query_features: dict, top_k: int = 5) -> list[dict]:
        """
        query_features に最も近い馬を top_k 件返す。
        Returns: [{"horse_id": ..., "score": ..., "meta": ...}, ...]
        """
        vec = embed_horse(query_features)

        if self._backend == "chromadb":
            results = self._col.query(query_embeddings=[vec], n_results=top_k)
            hits = []
            for i, hid in enumerate(results["ids"][0]):
                hits.append({
                    "horse_id": hid,
                    "score":    1.0 - results["distances"][0][i],
                    "meta":     results["metadatas"][0][i],
                })
            return hits

        elif self._backend == "faiss":
            import numpy as np
            arr = np.array([vec], dtype=np.float32)
            distances, indices = self._faiss_index.search(arr, top_k)
            hits = []
            for dist, idx in zip(distances[0], indices[0]):
                if idx < 0:
                    continue
                meta = self._faiss_meta[idx]
                hits.append({
                    "horse_id": meta.get("horse_id", str(idx)),
                    "score":    float(1.0 / (1.0 + dist)),
                    "meta":     meta,
                })
            return hits

        else:  # json
            return self._json_search(vec, top_k)

    def _json_search(self, query_vec: list[float], top_k: int) -> list[dict]:
        if not self._json_path.exists():
            return []
        records = []
        with open(self._json_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass

        scored = []
        for r in records:
            sim = cosine_similarity(query_vec, r.get("vector", []))
            scored.append({"horse_id": r["horse_id"], "score": sim, "meta": r.get("meta", {})})

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    # ------------------------------------------------------------------ #
    # ユーティリティ
    # ------------------------------------------------------------------ #

    def count(self) -> int:
        if self._backend == "chromadb":
            return self._col.count()
        elif self._backend == "faiss":
            return len(self._faiss_meta)
        else:
            if not self._json_path.exists():
                return 0
            return sum(1 for _ in open(self._json_path, encoding="utf-8"))

    def _save_faiss(self) -> None:
        import faiss, json
        faiss_path = STORE_DIR / f"{self.collection}.faiss"
        meta_path  = STORE_DIR / f"{self.collection}_meta.json"
        faiss.write_index(self._faiss_index, str(faiss_path))
        meta_path.write_text(json.dumps(self._faiss_meta, ensure_ascii=False), encoding="utf-8")

    def build_from_features_csv(self, csv_path: str | None = None) -> int:
        """
        keiba_data_features.csv から全馬の埋め込みを一括生成してストアに追加する。
        Returns: 追加した馬数
        """
        import pandas as pd
        path = csv_path or str(BASE_DIR / "keiba_data_features.csv")
        if not pathlib.Path(path).exists():
            log.warning("特徴量CSV が見つかりません: %s", path)
            return 0

        df = pd.read_csv(path, on_bad_lines="skip", low_memory=False)
        id_col = next((c for c in ["horse_id", "ketto_toroku_bango", "entry_id"] if c in df.columns), None)
        if id_col is None:
            log.warning("馬IDカラムが見つかりません")
            return 0

        count = 0
        for _, row in df.iterrows():
            horse_id = str(row[id_col])
            features = row.to_dict()
            self.add(horse_id, features, metadata={"source": "features_csv"})
            count += 1

        log.info("RAGStore.build_from_features_csv: %d 件追加", count)
        return count


# ================================================================== #
# シングルトンアクセサ
# ================================================================== #

_default_store: RAGStore | None = None


def get_default_store() -> RAGStore:
    global _default_store
    if _default_store is None:
        _default_store = RAGStore()
    return _default_store
