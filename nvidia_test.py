from openai import OpenAI

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key="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"
)

response = client.chat.completions.create(
    model="meta/llama-3.1-70b-instruct",
    messages=[{"role": "user", "content": "穴馬予想のコメントを生成して"}],
    temperature=0.7,
    max_tokens=1024
)
print(response.choices[0].message.content)
