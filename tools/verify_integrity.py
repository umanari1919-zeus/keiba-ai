#!/usr/bin/env python3
"""
うまなり地蔵AI 成果物整合性チェック。

重い DAG や再学習は実行せず、運用前に壊れてほしくない不変条件を確認する。
主な対象:
- 重要定数
- raw/features CSV の派生オッズ列混入
- model_v8.pkl の学習特徴量リーク
- レガシー LightGBM txt 成果物の学習特徴量リーク
- RAG JSON ストアの上限・重複・検索ID
"""

from __future__ import annotations

import argparse
import json
import pathlib
import pickle
import sys
from dataclasses import asdict, dataclass
from typing import Any

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.config import (
    ANABA_ODDS_RAW,
    BASE_DIR,
    CSV_FEATURES,
    CSV_RAW,
    EV_THRESHOLD,
    KELLY_FRACTION,
    LEAKY_DERIVED_FEATURE_COLUMNS,
    MIN_ODDS,
)
from pipeline.native_runtime import ensure_native_runtime


@dataclass
class IntegrityResult:
    name: str
    status: str
    detail: str


def _result(name: str, ok: bool, detail: str, warn: bool = False) -> IntegrityResult:
    return IntegrityResult(name=name, status="PASS" if ok else ("WARN" if warn else "FAIL"), detail=detail)


def check_constants() -> list[IntegrityResult]:
    expected = {
        "EV_THRESHOLD": (EV_THRESHOLD, 0.15),
        "KELLY_FRACTION": (KELLY_FRACTION, 0.10),
        "MIN_ODDS": (MIN_ODDS, 10.0),
        "ANABA_ODDS_RAW": (ANABA_ODDS_RAW, 300),
    }
    results: list[IntegrityResult] = []
    for name, (actual, wanted) in expected.items():
        results.append(_result(name=f"constant:{name}", ok=actual == wanted, detail=f"{actual!r}"))
    return results


def _read_csv_columns(path: str) -> list[str]:
    import pandas as pd

    return list(pd.read_csv(path, nrows=0, encoding="utf-8-sig", on_bad_lines="skip").columns)


def check_csv_headers() -> list[IntegrityResult]:
    results: list[IntegrityResult] = []
    for label, path in [("raw", CSV_RAW), ("features", CSV_FEATURES)]:
        csv_path = pathlib.Path(path)
        if not csv_path.exists():
            results.append(_result(f"csv:{label}", False, f"missing: {csv_path}"))
            continue
        cols = _read_csv_columns(str(csv_path))
        leaky = [c for c in LEAKY_DERIVED_FEATURE_COLUMNS if c in cols]
        results.append(_result(
            name=f"csv:{label}:derived-odds",
            ok=not leaky,
            detail=f"cols={len(cols)} leaky={leaky}",
        ))
    return results


def _is_leaky_feature(name: str) -> bool:
    normalized = name.lower()
    return any(token in normalized for token in ("odds", "ninki", "popular"))


def check_model() -> list[IntegrityResult]:
    model_path = pathlib.Path(BASE_DIR) / "model_v8.pkl"
    if not model_path.exists():
        return [_result("model:model_v8", False, f"missing: {model_path}")]

    ensure_native_runtime()
    with model_path.open("rb") as f:
        model: Any = pickle.load(f)

    features = model.get("features", []) if isinstance(model, dict) else []
    leaky = [feature for feature in features if _is_leaky_feature(str(feature))]
    metrics = model.get("metrics", {}) if isinstance(model, dict) else {}
    metric_hint = ""
    if metrics:
        metric_hint = f" ensemble_acc={metrics.get('ensemble_acc', 'N/A')}"
    return [
        _result(
            name="model:features",
            ok=bool(features) and not leaky,
            detail=f"features={len(features)} leaky={leaky}{metric_hint}",
        )
    ]


def check_legacy_lightgbm_txt() -> list[IntegrityResult]:
    model_path = pathlib.Path(BASE_DIR) / "pipeline_v2" / "model_lgbm_v2.txt"
    if not model_path.exists():
        return [_result("model:legacy-lgbm-txt", True, "absent")]

    feature_names: list[str] = []
    with model_path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("feature_names="):
                feature_names = line.strip().split("=", 1)[1].split()
                break

    leaky = [feature for feature in feature_names if _is_leaky_feature(feature)]
    return [
        _result(
            name="model:legacy-lgbm-txt",
            ok=bool(feature_names) and not leaky,
            detail=f"features={len(feature_names)} leaky={leaky}",
        )
    ]


def _rag_doc_id(record: dict) -> str:
    return str(record.get("horse_id") or record.get("meta", {}).get("doc_id") or "")


def check_rag(rag_max: int) -> list[IntegrityResult]:
    rag_path = pathlib.Path(BASE_DIR) / "data" / "rag_store" / "umanari_horses.jsonl"
    if not rag_path.exists():
        return [_result("rag:store", False, f"missing: {rag_path}")]

    ids: list[str] = []
    json_errors = 0
    with rag_path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                json_errors += 1
                continue
            ids.append(_rag_doc_id(record))

    unique_count = len(set(ids))
    duplicates = len(ids) - unique_count
    results = [
        _result("rag:json", json_errors == 0, f"json_errors={json_errors}"),
        _result("rag:size", 0 < len(ids) <= rag_max, f"lines={len(ids)} max={rag_max}"),
        _result("rag:duplicates", duplicates == 0, f"unique={unique_count} duplicates={duplicates}"),
    ]

    try:
        from agents.rag_store import get_default_store

        store = get_default_store()
        hits = store.search({
            "win_rate": 0.1,
            "past3_avg_chakujun": 3,
            "futan_juryo": 55,
            "bataiju": 480,
            "odds": 9999,  # embed_horse 側で無視されることを期待
        }, top_k=3)
        bad_ids = [h.get("horse_id", "") for h in hits if str(h.get("horse_id", "")).startswith("row:")]
        missing_doc_ids = [h for h in hits if not h.get("doc_id")]
        results.append(_result(
            "rag:search-id",
            bool(hits) and not bad_ids and not missing_doc_ids,
            f"hits={len(hits)} bad_horse_ids={bad_ids} missing_doc_ids={len(missing_doc_ids)}",
        ))
    except Exception as exc:
        results.append(_result("rag:search-id", False, f"search failed: {exc}"))

    return results


def run_checks(rag_max: int) -> list[IntegrityResult]:
    return [
        *check_constants(),
        *check_csv_headers(),
        *check_model(),
        *check_legacy_lightgbm_txt(),
        *check_rag(rag_max),
    ]


def print_report(results: list[IntegrityResult]) -> None:
    print("=" * 72)
    print("Umanari integrity check")
    print("=" * 72)
    for item in results:
        print(f"[{item.status}] {item.name:<28} {item.detail}")
    pass_count = sum(1 for item in results if item.status == "PASS")
    warn_count = sum(1 for item in results if item.status == "WARN")
    fail_count = sum(1 for item in results if item.status == "FAIL")
    print("-" * 72)
    print(f"PASS {pass_count}/{len(results)}  WARN {warn_count}  FAIL {fail_count}")


def main() -> int:
    parser = argparse.ArgumentParser(description="うまなり地蔵AI 成果物整合性チェック")
    parser.add_argument("--json", action="store_true", help="JSON で出力")
    parser.add_argument("--rag-max", type=int, default=50000, help="RAG JSON ストアの想定最大件数")
    args = parser.parse_args()

    results = run_checks(rag_max=args.rag_max)
    if args.json:
        print(json.dumps([asdict(item) for item in results], ensure_ascii=False, indent=2))
    else:
        print_report(results)
    return 0 if all(item.status != "FAIL" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
