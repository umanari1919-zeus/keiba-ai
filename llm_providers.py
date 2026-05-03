"""
llm_providers.py
================
複数の無料LLMプロバイダを統一インターフェースで扱うモジュール。

Gemini / Groq / Ollama を1つの `chat(prompt, provider=...)` 関数で呼び出せる。
1つが quota 切れになっても自動で次のプロバイダにフォールバックする。

使い方:
    from llm_providers import LLMRouter
    router = LLMRouter()
    answer = router.chat("競馬の話を一言で")           # 自動選択
    answer = router.chat("...", provider="gemini")    # 指定
    answer = router.chat("...", provider="groq")
    answer = router.chat("...", provider="ollama")
"""

from __future__ import annotations
import os
from typing import Optional
from dotenv import load_dotenv

# .env を読み込む
load_dotenv()


class LLMRouter:
    """複数プロバイダのフォールバック付きLLMルーター"""

    def __init__(self):
        self.gemini_key  = os.getenv("GEMINI_API_KEY", "").strip()
        self.groq_key    = os.getenv("GROQ_API_KEY", "").strip()
        self.ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").strip()
        self.default_provider = os.getenv("DEFAULT_LLM_PROVIDER", "gemini").strip()
        self.default_ollama   = os.getenv("DEFAULT_OLLAMA_MODEL", "gemma2:2b").strip()

        # 利用可能プロバイダ判定
        self.available = []
        if self.gemini_key:  self.available.append("gemini")
        if self.groq_key:    self.available.append("groq")
        # Ollama は接続テストで判定
        if self._check_ollama(): self.available.append("ollama")

    # ---- ヘルスチェック ----
    def _check_ollama(self) -> bool:
        try:
            import requests
            r = requests.get(f"{self.ollama_host}/api/tags", timeout=2)
            return r.status_code == 200
        except Exception:
            return False

    def status(self) -> dict:
        return {
            "available": self.available,
            "default": self.default_provider,
            "gemini_key": bool(self.gemini_key),
            "groq_key":   bool(self.groq_key),
            "ollama_host": self.ollama_host,
        }

    # ---- 個別プロバイダ呼び出し ----
    def _gemini(self, prompt: str, model: str = "gemini-2.0-flash") -> str:
        import google.generativeai as genai
        genai.configure(api_key=self.gemini_key)
        gm = genai.GenerativeModel(model)
        return gm.generate_content(prompt).text.strip()

    def _groq(self, prompt: str, model: str = "llama-3.3-70b-versatile") -> str:
        from groq import Groq
        client = Groq(api_key=self.groq_key)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1024,
        )
        return resp.choices[0].message.content.strip()

    def _ollama(self, prompt: str, model: Optional[str] = None) -> str:
        import ollama
        client = ollama.Client(host=self.ollama_host)
        m = model or self.default_ollama
        r = client.chat(model=m, messages=[{"role": "user", "content": prompt}])
        return r["message"]["content"].strip()

    # ---- 統一インターフェース ----
    def chat(self, prompt: str, provider: Optional[str] = None,
             model: Optional[str] = None, fallback: bool = True) -> str:
        """
        プロンプトを送信して応答を返す。
        provider 未指定なら DEFAULT_LLM_PROVIDER → 利用可能な順 で自動選択。
        fallback=True の場合、失敗時に他プロバイダを試す。
        """
        if not self.available:
            raise RuntimeError("利用可能なLLMプロバイダがありません。.env を確認してください。")

        order = []
        if provider:
            order.append(provider)
        else:
            # 既定 → 残り
            if self.default_provider in self.available:
                order.append(self.default_provider)
            for p in self.available:
                if p not in order:
                    order.append(p)

        last_err = None
        for p in order:
            if p not in self.available:
                continue
            try:
                if p == "gemini":
                    return self._gemini(prompt, model or "gemini-2.0-flash")
                elif p == "groq":
                    return self._groq(prompt, model or "llama-3.3-70b-versatile")
                elif p == "ollama":
                    return self._ollama(prompt, model)
            except Exception as e:
                last_err = e
                if not fallback:
                    raise
                print(f"  [{p}] 失敗 → 次のプロバイダへ ({type(e).__name__})")
                continue

        raise RuntimeError(f"全プロバイダ失敗: {last_err}")


if __name__ == "__main__":
    router = LLMRouter()
    print("[LLM Status]")
    for k, v in router.status().items():
        print(f"  {k}: {v}")
    print()
    if router.available:
        print(">> テストプロンプト送信中: 'こんにちは。一言で自己紹介してください。'")
        print(f">> 応答: {router.chat('こんにちは。一言で自己紹介してください。')}")
    else:
        print("利用可能なプロバイダがありません。llm_setup.md の手順を実行してください。")
