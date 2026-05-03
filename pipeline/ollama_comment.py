"""
ollama_comment.py  --  Ollama (local LLM) 競馬予想コメント生成
============================================================================
Ollama REST API (localhost:11434) を使って日本語の競馬予想コメントを生成する。
Ollamaが未起動の場合は Claude Haiku API にフォールバック。

## タスク別モデルプロファイル

  "japanese" -- 日本語生成（X投稿・note記事・解説）
      推奨: qwen2.5:7b / aya-expanse:8b / gemma3:12b
  "json"     -- 構造化出力（Supervisor・知見抽出）
      推奨: deepseek-r1:7b / phi4:14b / qwen2.5:7b
  "fast"     -- 高速バッチ（並列生成・大量処理）
      推奨: qwen2.5:1.5b / gemma3:1b / deepseek-r1:1.5b

## RAM別推奨インストール

  ~2GB 空き: ollama pull qwen2.5:1.5b   (軽量・高速)
  ~2GB 空き: ollama pull deepseek-r1:1.5b (推論強化)
  ~4GB 空き: ollama pull qwen2.5:3b      (バランス型・推奨)
  ~5GB 空き: ollama pull qwen2.5:7b      (日本語最強)
  ~5GB 空き: ollama pull aya-expanse:8b  (多言語特化)
  ~5GB 空き: ollama pull deepseek-r1:7b  (構造出力最強)

Usage:
    python pipeline/ollama_comment.py            # test mode
    python pipeline/ollama_comment.py --models   # インストール済みモデル一覧
    from pipeline.ollama_comment import generate_comment, generate_picks_post
    from pipeline.ollama_comment import get_model_for_task
"""
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List, Dict

import requests

OLLAMA_BASE = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
TIMEOUT     = 120  # seconds

# ─────────────────────────────────────────────────────────────
# タスク別モデルプロファイル
# ─────────────────────────────────────────────────────────────

# "japanese": 日本語生成（X投稿・note記事・解説）
JAPANESE_MODELS = [
    "qwen2.5:14b",       # 最高品質日本語（RAM ~9GB）
    "aya-expanse:8b",    # 多言語特化・日本語優秀（RAM ~5GB）
    "qwen2.5:7b",        # 高品質日本語（RAM ~5GB）★推奨
    "gemma3:12b",        # Google最新・日本語良好（RAM ~8GB）
    "gemma3:4b",         # Google最新・軽量（RAM ~3GB）
    "qwen2.5:3b",        # バランス型（RAM ~2GB）
    "gemma2:9b",         # 旧世代だが安定（RAM ~6GB）
    "gemma2:2b",         # 超軽量（RAM ~1.5GB）
    "llama3.2:3b",       # Meta軽量（RAM ~2GB）
    "llama3.1:8b",       # Meta標準（RAM ~5GB）
    "mistral:7b",        # フランス発・多言語（RAM ~4GB）
    "mistral-nemo:12b",  # Mistral最新（RAM ~7GB）
    "qwen2.5:1.5b",      # 最軽量（RAM ~1GB）
    "llama3.2:1b",       # 最軽量Meta（RAM ~0.6GB）
]

# "json": 構造化出力（Supervisor判断・知見抽出・重複判定）
JSON_MODELS = [
    "deepseek-r1:7b",    # 推論特化・JSON出力優秀（RAM ~5GB）★推奨
    "deepseek-r1:14b",   # 大型推論モデル（RAM ~9GB）
    "phi4:14b",          # Microsoft・構造出力強い（RAM ~9GB）
    "phi4-mini:3.8b",    # phi4軽量版（RAM ~2.5GB）
    "phi3.5:3.8b",       # phi3.5（RAM ~2.5GB）
    "qwen2.5:7b",        # JSON出力も得意（RAM ~5GB）
    "deepseek-r1:1.5b",  # 超軽量推論（RAM ~1GB）
    "qwen2.5:3b",        # 軽量JSON（RAM ~2GB）
    "gemma3:4b",         # 新世代軽量（RAM ~3GB）
    "llama3.2:3b",       # フォールバック（RAM ~2GB）
]

# "fast": 高速バッチ並列生成
FAST_MODELS = [
    "qwen2.5:1.5b",      # 最速・高品質（RAM ~1GB）★推奨
    "deepseek-r1:1.5b",  # 最速推論（RAM ~1GB）
    "gemma3:1b",         # Google最速（RAM ~0.7GB）
    "llama3.2:1b",       # Meta最速（RAM ~0.6GB）
    "gemma2:2b",         # 旧世代最速（RAM ~1.5GB）
    "qwen2.5:3b",        # 速度×品質バランス（RAM ~2GB）
    "llama3.2:3b",       # フォールバック（RAM ~2GB）
]

# デフォルト（後方互換: 従来のMODEL_PRIORITYと同等）
MODEL_PRIORITY = JAPANESE_MODELS

# タスク → プロファイル マッピング
_TASK_PROFILES: Dict[str, List[str]] = {
    "japanese": JAPANESE_MODELS,
    "comment":  JAPANESE_MODELS,   # alias
    "json":     JSON_MODELS,
    "analysis": JSON_MODELS,       # alias
    "fast":     FAST_MODELS,
    "batch":    FAST_MODELS,       # alias
    "default":  MODEL_PRIORITY,
}

# モデルキャッシュ（タスク別）
_model_cache: Dict[str, Optional[str]] = {}
_cached_model: Optional[str] = None  # 後方互換


# ─────────────────────────────────────────────────────────────
# Model detection
# ─────────────────────────────────────────────────────────────

def _get_installed_models() -> tuple:
    """
    Ollamaからインストール済みモデル一覧を取得。
    Returns: (installed_full: set, base_to_installed: dict, models_data: list)
    """
    resp = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=5)
    if resp.status_code != 200:
        return set(), {}, []
    models_data = resp.json().get("models", [])
    installed_full = {m["name"] for m in models_data}
    base_to_installed: Dict[str, str] = {}
    for m in models_data:
        base = m["name"].split(":")[0]
        if base not in base_to_installed:
            base_to_installed[base] = m["name"]
    return installed_full, base_to_installed, models_data


def _pick_from_priority(priority: List[str],
                        installed_full: set,
                        base_to_installed: Dict) -> Optional[str]:
    """優先リストからインストール済みの最初のモデルを返す。"""
    for model in priority:
        base = model.split(":")[0]
        if model in installed_full:
            return model
        elif base in base_to_installed:
            return base_to_installed[base]
    return None


def get_model_for_task(task: str = "default") -> Optional[str]:
    """
    タスクに最適なモデルを返す。キャッシュあり。

    Args:
        task: "japanese" | "json" | "fast" | "default"
              "comment"/"analysis"/"batch" も可（alias）

    Returns:
        モデル名（例: "qwen2.5:3b"）、見つからなければ None
    """
    global _model_cache
    if task in _model_cache:
        return _model_cache[task]
    try:
        installed_full, base_to_installed, _ = _get_installed_models()
        if not installed_full:
            return None
        priority = _TASK_PROFILES.get(task, MODEL_PRIORITY)
        model = _pick_from_priority(priority, installed_full, base_to_installed)
        if model:
            print(f"  [ollama] task={task} model={model}")
        _model_cache[task] = model
        return model
    except Exception:
        return None


def get_available_model() -> Optional[str]:
    """後方互換: デフォルトプロファイルの最適モデルを返す。"""
    global _cached_model
    if _cached_model:
        return _cached_model
    model = get_model_for_task("japanese")
    if model:
        _cached_model = model
    return model


def list_installed_models() -> List[Dict]:
    """
    インストール済みモデルの一覧を返す。
    Returns: [{"name": str, "size_gb": float, "family": str}, ...]
    """
    try:
        _, _, models_data = _get_installed_models()
        result = []
        for m in models_data:
            name = m["name"]
            family = name.split(":")[0]
            size_gb = round(m.get("size", 0) / 1e9, 1)
            result.append({"name": name, "size_gb": size_gb, "family": family})
        return sorted(result, key=lambda x: x["size_gb"])
    except Exception:
        return []


def print_model_status():
    """インストール済みモデルとタスク別選定結果を表示。"""
    print("\n=== Ollama モデル状況 ===")
    if not is_ollama_running():
        print("  ❌ Ollama 未起動 (ollama serve を実行してください)")
        return

    models = list_installed_models()
    if not models:
        print("  ⚠️ インストール済みモデルなし")
        print("  推奨: ollama pull qwen2.5:3b")
        return

    print(f"  インストール済み: {len(models)}モデル")
    for m in models:
        print(f"    {m['name']:30s} {m['size_gb']:.1f}GB")

    print("\n  タスク別選定:")
    # キャッシュをクリアして再検索
    global _model_cache
    _model_cache = {}
    for task in ["japanese", "json", "fast"]:
        model = get_model_for_task(task)
        label = {"japanese": "日本語生成", "json": "構造出力",
                 "fast": "高速バッチ"}[task]
        status = model if model else "なし（モデルをインストールしてください）"
        print(f"    {label:12s}: {status}")


def is_ollama_running() -> bool:
    try:
        r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def pull_model(model: str) -> bool:
    """Pull a model if not already installed."""
    print(f"  [ollama] pulling {model} ...")
    try:
        resp = requests.post(
            f"{OLLAMA_BASE}/api/pull",
            json={"name": model, "stream": False},
            timeout=600,
        )
        return resp.status_code == 200
    except Exception as e:
        print(f"  [ollama] pull failed: {e}")
        return False


# ─────────────────────────────────────────────────────────────
# Core generation  (streaming + non-streaming)
# ─────────────────────────────────────────────────────────────

def _generate(prompt: str, system: str = "", model: str = None,
              temperature: float = 0.7, stream: bool = True,
              task: str = "japanese") -> Optional[str]:
    """
    Call Ollama /api/generate and return text.

    Args:
        prompt:      ユーザープロンプト
        system:      システムプロンプト
        model:       モデル名（None でタスク別自動選定）
        temperature: 生成温度（0.0〜1.0）
        stream:      True=トークン逐次表示（UX向上）/ False=並列用
        task:        "japanese"|"json"|"fast"|"default" (model=None時に使用)

    Returns:
        生成テキスト（失敗時はNone）
    """
    if model is None:
        model = get_model_for_task(task)
    if not model:
        return None

    payload = {
        "model":  model,
        "prompt": prompt,
        "system": system,
        "stream": stream,
        "options": {
            "temperature":  temperature,
            "num_predict":  512,
            "top_p":        0.9,
            "repeat_penalty": 1.1,
        },
    }
    try:
        t0 = time.time()
        if stream:
            # streaming: print tokens as they arrive
            resp = requests.post(
                f"{OLLAMA_BASE}/api/generate",
                json=payload,
                timeout=TIMEOUT,
                stream=True,
            )
            if resp.status_code != 200:
                print(f"  [ollama] HTTP {resp.status_code}: {resp.text[:100]}")
                return None
            collected = []
            print("  ", end="", flush=True)
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                    token = chunk.get("response", "")
                    if token:
                        print(token, end="", flush=True)
                        collected.append(token)
                    if chunk.get("done"):
                        break
                except json.JSONDecodeError:
                    continue
            print()  # newline after stream
            text = "".join(collected).strip()
            elapsed = time.time() - t0
            print(f"  [ollama] {len(text)}chars in {elapsed:.1f}s")
            return text
        else:
            # non-streaming: for parallel/background use
            resp = requests.post(
                f"{OLLAMA_BASE}/api/generate",
                json=payload,
                timeout=TIMEOUT,
            )
            elapsed = time.time() - t0
            if resp.status_code == 200:
                text = resp.json().get("response", "").strip()
                return text
            else:
                print(f"  [ollama] HTTP {resp.status_code}: {resp.text[:100]}")
                return None
    except Exception as e:
        print(f"  [ollama] error: {e}")
        return None


def _generate_parallel(tasks: List[dict],
                        task_type: str = "fast") -> List[Optional[str]]:
    """
    \u8907\u6570\u306e\u30d7\u30ed\u30f3\u30d7\u30c8\u3092\u4e26\u5217\u751f\u6210\u3059\u308b\u3002
    tasks: [{"prompt": str, "system": str, "temperature": float}, ...]
    task_type: "fast"\uff08\u30c7\u30d5\u30a9\u30eb\u30c8\u30fb\u8efd\u91cf\u30e2\u30c7\u30eb\uff09/ "japanese" / "json"
    Returns: \u540c\u9806\u306e\u751f\u6210\u7d50\u679c\u30ea\u30b9\u30c8

    \u6ce8\u610f: CPU \u306e\u307f\u74b0\u5883\u3067\u306f Ollama \u304c\u30b7\u30f3\u30b0\u30eb\u30b9\u30ec\u30c3\u30c9\u306e\u305f\u3081
          \u5b9f\u969b\u306e\u4e26\u5217\u5316\u52b9\u679c\u306f\u9650\u5b9a\u7684\u3002\u305f\u3060\u3057\u975e\u540c\u671f\u5f85\u6a5f\u3067 UI \u3092\u6b62\u3081\u306a\u3044\u3002
    """
    model = get_model_for_task(task_type)
    if not model:
        return [None] * len(tasks)

    results: List[Optional[str]] = [None] * len(tasks)

    def _call_one(idx: int, t: dict) -> tuple:
        text = _generate(
            prompt=t.get("prompt", ""),
            system=t.get("system", ""),
            model=model,
            temperature=t.get("temperature", 0.7),
            stream=False,
            task=task_type,
        )
        return idx, text

    max_workers = min(2, len(tasks))
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_call_one, i, t): i for i, t in enumerate(tasks)}
        for fut in as_completed(futures):
            try:
                idx, text = fut.result()
                results[idx] = text
            except Exception as e:
                print(f"  [ollama] parallel error: {e}")

    return results


# \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
# Public API
# \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

def generate_comment(horse_name: str, odds: float, rank: int,
                     extra: str = "") -> Optional[str]:
    """
    \u9a6c1\u982d\u306eX\u6295\u7a3f\u30b3\u30e1\u30f3\u30c8\u3092\u751f\u6210\u3059\u308b\u3002

    Args:
        horse_name: \u99c6\u540d
        odds:       \u5358\u52dd\u30aa\u30c3\u30ba
        rank:       \u4eba\u6c17\u9806\u4f4d
        extra:      \u8ffd\u52a0\u60c5\u5831\uff08\u8abf\u6559\u30b3\u30e1\u30f3\u30c8\u306a\u3069\uff09

    Returns:
        140\u5b57\u4ee5\u5185\u306e\u3064\u3076\u3084\u304d\u30c6\u30ad\u30b9\u30c8\uff08\u5931\u6557\u6642 None\uff09
    """
    system = (
        "\u3042\u306a\u305f\u306f\u6c17\u9803\u306a\u7af6\u99ac\u4e88\u60f3\u5c5a\u3067\u3059\u3002\n"
        "X\uff08\u65e7Twitter\uff09\u306b\u6295\u7a3f\u3059\u308b140\u5b57\u4ee5\u5185\u306e\u77ed\u3044\u3064\u3076\u3084\u304d\u3092\u6295\u7a3f\u3057\u3066\u304f\u3060\u3055\u3044\u3002\n"
        "\u7af6\u99ac\u306e\u7a74\u99ac\u60c5\u5831\u3092\u571f\u5730\u3063\u5146\u3067\u5c45\u52d9\u3088\u304f\u4f1d\u3048\u3066\u304f\u3060\u3055\u3044\u3002\n"
        "\u30cf\u30c3\u30b7\u30e5\u30bf\u30b0\u306f #\u7af6\u99ac\u4e88\u60f3 #\u7a74\u99ac \u3092\u5fc5\u305a\u5165\u308c\u3066\u304f\u3060\u3055\u3044\u3002\n"
        "\u65e5\u672c\u8a9e\u3067\u56de\u7b54\u3057\u3066\u304f\u3060\u3055\u3044\u3002"
    )
    odds_str = str(odds)
    rank_str = str(rank)
    extra_part = ("\n\u8ffd\u52a0\u60c5\u5831: " + extra) if extra else ""
    prompt = (
        "\u6b21\u306e\u99ac\u306eX\u6295\u7a3f\u30b3\u30e1\u30f3\u30c8\u3092140\u5b57\u4ee5\u5185\u3067\u751f\u6210\u3057\u3066\u304f\u3060\u3055\u3044\u3002\n\n"
        "\u99c6\u540d: " + horse_name + "\n"
        "\u5358\u52dd\u30aa\u30c3\u30ba: " + odds_str + "\u500d\n"
        "\u4eba\u6c17\u9806\u4f4d: " + rank_str + "\u756a\u4eba\u6c17" +
        extra_part
    )
    return _generate(prompt, system, temperature=0.8, task="japanese")


def generate_picks_post(picks: list) -> Optional[str]:
    """
    \u8907\u6570\u99ac\u306e\u7a74\u99ac\u4e88\u60f3X\u6295\u7a3f\u672c\u6587\u3092\u751f\u6210\u3059\u308b\u3002

    Args:
        picks: [{"horse": str, "odds": float, "ev": float}, ...] \u5f62\u5f0f\u306e\u30ea\u30b9\u30c8

    Returns:
        280\u5b57\u4ee5\u5185\u306eX\u6295\u7a3f\u672c\u6587\uff08\u5931\u6557\u6642 None\uff09
    """
    if not picks:
        return None
    system = (
        "\u3042\u306a\u305f\u306f\u6c17\u9803\u306a\u7af6\u99ac\u4e88\u60f3\u5c5a\u3067\u3059\u3002\n"
        "X\uff08\u65e7Twitter\uff09\u306b\u6295\u7a3f\u3059\u308b280\u5b57\u4ee5\u5185\u306e\u4e88\u60f3\u3064\u3076\u3084\u304d\u3092\u6295\u7a3f\u3057\u3066\u304f\u3060\u3055\u3044\u3002\n"
        "\u30cf\u30c3\u30b7\u30e5\u30bf\u30b0: #\u7af6\u99ac\u4e88\u60f3 #\u7a74\u99ac #\u7a74\u99ac\u767a\u6398\n"
        "\u65e5\u672c\u8a9e\u3067\u56de\u7b54\u3057\u3066\u304f\u3060\u3055\u3044\u3002"
    )
    lines = []
    for i, p in enumerate(picks[:5], 1):
        h = p.get("horse", "?")
        o = str(p.get("odds", "?"))
        e = str(round(p.get("ev", 0) * 100))
        lines.append(str(i) + ". " + h + " (" + o + "\u500d / EV+" + e + "%)")
    picks_str = "\n".join(lines)
    prompt = (
        "\u4eca\u65e5\u306e\u7a74\u99ac\u4e88\u60f3\u3092X\u306b\u6295\u7a3f\u3057\u3066\u304f\u3060\u3055\u3044\u3002\n\n"
        "\u4e88\u60f3\u99ac:\n" + picks_str + "\n\n"
        "\u9b45\u529b\u7684\u306a280\u5b57\u4ee5\u5185\u306e\u3064\u3076\u3084\u304d\u3092\u4f5c\u6210\u3057\u3066\u304f\u3060\u3055\u3044\u3002"
    )
    return _generate(prompt, system, temperature=0.85, task="japanese")


def generate_race_analysis(race_name: str, picks: list,
                            context: str = "") -> Optional[str]:
    """
    \u30ec\u30fc\u30b9\u5206\u6790\u30b3\u30e1\u30f3\u30c8\u3092\u751f\u6210\u3059\u308b\u3002

    Args:
        race_name: \u30ec\u30fc\u30b9\u540d
        picks:     [{"horse": str, "odds": float, "reason": str}, ...]
        context:   \u8ffd\u52a0\u30b3\u30f3\u30c6\u30ad\u30b9\u30c8\uff08\u5929\u6c17\u30fb\u99c6\u5834\u60c5\u5831\u306a\u3069\uff09

    Returns:
        note.com \u8a18\u4e8b\u7528\u5206\u6790\u30c6\u30ad\u30b9\u30c8\uff08\u5931\u6557\u6642 None\uff09
    """
    system = (
        "\u3042\u306a\u305f\u306f\u30c7\u30fc\u30bf\u9a71\u52d5\u306e\u7af6\u99ac\u5206\u6790\u306e\u30d7\u30ed\u3067\u3059\u3002\n"
        "AI\u3068ML\u3092\u6d3b\u7528\u3057\u305f\u79d1\u5b66\u7684\u306a\u89b3\u70b9\u304b\u3089\u30ec\u30fc\u30b9\u3092\u5206\u6790\u3057\u3066\u304f\u3060\u3055\u3044\u3002\n"
        "note.com\u8a18\u4e8b\u306e\u5206\u6790\u30bb\u30af\u30b7\u30e7\u30f3\uff08300\u5b57\u7a0b\u5ea6\uff09\u3068\u3057\u3066\u66f8\u3044\u3066\u304f\u3060\u3055\u3044\u3002\n"
        "\u65e5\u672c\u8a9e\u3067\u56de\u7b54\u3057\u3066\u304f\u3060\u3055\u3044\u3002"
    )
    lines = []
    for p in picks[:5]:
        h = p.get("horse", "?")
        o = str(p.get("odds", "?"))
        r = p.get("reason", "")
        if r:
            lines.append("\u30fb" + h + "\uff08" + o + "\u500d\uff09: " + r)
        else:
            lines.append("\u30fb" + h + "\uff08" + o + "\u500d\uff09")
    picks_str = "\n".join(lines)
    ctx_part = ("\n\n\u30b3\u30f3\u30c6\u30ad\u30b9\u30c8: " + context) if context else ""
    prompt = (
        "\u30ec\u30fc\u30b9: " + race_name + "\n\n"
        "\u6ce8\u76ee\u99ac:\n" + picks_str +
        ctx_part + "\n\n"
        "\u3053\u306e\u30ec\u30fc\u30b9\u306e\u5206\u6790\u30b3\u30e1\u30f3\u30c8\u3092300\u5b57\u7a0b\u5ea6\u3067\u66f8\u3044\u3066\u304f\u3060\u3055\u3044\u3002"
    )
    return _generate(prompt, system, temperature=0.75, task="japanese")


def generate_comments_batch(horses: list) -> List[Optional[str]]:
    """
    \u8907\u6570\u99ac\u306e\u30b3\u30e1\u30f3\u30c8\u3092\u4e26\u5217\u751f\u6210\u3059\u308b\u3002

    Args:
        horses: [{"name": str, "odds": float, "rank": int, "extra": str}, ...]

    Returns:
        \u540c\u9806\u306e\u30b3\u30e1\u30f3\u30c8\u30ea\u30b9\u30c8\uff08\u5931\u6557\u6642 None\uff09
    """
    tasks = []
    for h in horses:
        name = h.get("name", "?")
        odds_val = str(h.get("odds", "?"))
        rank_val = str(h.get("rank", "?"))
        extra_val = h.get("extra", "")
        prompt = (
            "\u7af6\u99ac\u4e88\u60f3\u30b3\u30e1\u30f3\u30c8\u3092140\u5b57\u4ee5\u5185\u3067\u3002\n"
            "\u99c6: " + name + " / \u30aa\u30c3\u30ba: " + odds_val + "\u500d / \u4eba\u6c17" + rank_val + "\u756a"
            + ("/ " + extra_val if extra_val else "")
        )
        tasks.append({"prompt": prompt,
                      "system": "\u65e5\u672c\u8a9e\u306e\u7af6\u99ac\u4e88\u60f3\u5c5a\u3002140\u5b57\u4ee5\u5185\u306eX\u6295\u7a3f\u30b3\u30e1\u30f3\u30c8\u3002#\u7af6\u99ac\u4e88\u60f3 \u5fc5\u9808\u3002",
                      "temperature": 0.8})
    # \u30d0\u30c3\u30c1\u5f62\u5f0f\u306f fast \u30d7\u30ed\u30d5\u30a1\u30a4\u30eb\uff08\u8efd\u91cf\u30e2\u30c7\u30eb\uff09
    return _generate_parallel(tasks, task_type="fast")


# \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
# CLI entry point
# \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

if __name__ == "__main__":
    if "--models" in sys.argv:
        # \u30a4\u30f3\u30b9\u30c8\u30fc\u30eb\u6e08\u307f\u30e2\u30c7\u30eb\u4e00\u89a7\u3068\u30bf\u30b9\u30af\u5225\u9078\u5b9a\u7d50\u679c\u3092\u8868\u793a
        print_model_status()
        sys.exit(0)

    print("=== ollama_comment.py \u30c6\u30b9\u30c8 ===")
    if not is_ollama_running():
        print("\u26a0\ufe0f  Ollama \u304c\u8d77\u52d5\u3057\u3066\u3044\u307e\u305b\u3093\u3002")
        print("   \u5b9f\u884c\u65b9\u6cd5: ollama serve")
        sys.exit(1)

    # \u30b7\u30f3\u30b0\u30eb\u30b3\u30e1\u30f3\u30c8 (japanese \u30d7\u30ed\u30d5\u30a1\u30a4\u30eb)
    print("\n[1] \u99c6\u5358\u4f53\u30b3\u30e1\u30f3\u30c8 (task=japanese)")
    result = generate_comment("\u30c6\u30b9\u30c8\u30de\u30fc\u30af", 25.4, 8, "\u524d\u8d70\u597d\u8abf")
    if result:
        print("\n=> " + result[:100])
    else:
        print("  \u751f\u6210\u5931\u6557")

    # \u8907\u6570\u99ac\u30d0\u30c3\u30c1 (fast \u30d7\u30ed\u30d5\u30a1\u30a4\u30eb)
    print("\n[2] \u30d0\u30c3\u30c1\u30b3\u30e1\u30f3\u30c8 (task=fast)")
    horses = [
        {"name": "\u30a6\u30de\u30ca\u30ea\u30c6\u30b9\u30c8A", "odds": 18.3, "rank": 10},
        {"name": "\u30a6\u30de\u30ca\u30ea\u30c6\u30b9\u30c8B", "odds": 32.1, "rank": 14},
    ]
    results = generate_comments_batch(horses)
    for i, r in enumerate(results):
        name_i = horses[i]["name"]
        if r:
            print("  " + name_i + ": " + r[:60])
        else:
            print("  " + name_i + ": \u5931\u6557")

    # \u30ec\u30fc\u30b9\u5206\u6790 (japanese \u30d7\u30ed\u30d5\u30a1\u30a4\u30eb)
    print("\n[3] \u30ec\u30fc\u30b9\u5206\u6790 (task=japanese)")
    analysis = generate_race_analysis(
        "\u30c6\u30b9\u30c8\u30ec\u30fc\u30b9",
        [{"horse": "\u30a2", "odds": 15.0, "reason": "EV+32%"}],
        "\u826f\u99ac\u5834\u8fba"
    )
    if analysis:
        print("  " + analysis[:120])
    else:
        print("  \u751f\u6210\u5931\u6557")

    print("\n=== \u5b8c\u4e86 ===")
