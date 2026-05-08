import os
from openai import OpenAI

api_key = os.getenv("NVIDIA_API_KEY")
if not api_key:
    raise SystemExit("NVIDIA_API_KEY が環境変数に設定されていません。.env を確認してください。")

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=api_key,
)

response = client.chat.completions.create(
    model="meta/llama-3.1-70b-instruct",
    messages=[{"role": "user", "content": "穴馬予想のコメントを生成して"}],
    temperature=0.7,
    max_tokens=1024
)
print(response.choices[0].message.content)
