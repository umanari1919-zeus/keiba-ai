import importlib.metadata as meta

extra = [
    "psycopg2-binary", "psycopg2", "python-dotenv", "dotenv",
    "playwright", "anthropic", "langgraph", "stable-baselines3",
    "ollama", "torch", "gymnasium",
]
for p in extra:
    try:
        v = meta.version(p)
        print(f"{p}=={v}")
    except meta.PackageNotFoundError:
        print(f"# {p} not installed")
