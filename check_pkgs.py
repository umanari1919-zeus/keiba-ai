import importlib.metadata as meta

pkgs = [
    "psycopg2", "sqlalchemy", "pandas", "numpy",
    "lightgbm", "xgboost", "catboost", "scikit-learn",
    "optuna", "shap", "httpx", "beautifulsoup4", "playwright",
    "anthropic", "schedule", "streamlit", "langgraph",
    "stable-baselines3", "python-dotenv", "pyarrow",
    "requests", "matplotlib", "scipy",
]
for p in pkgs:
    try:
        v = meta.version(p)
        print(f"{p}=={v}")
    except meta.PackageNotFoundError:
        print(f"# {p} not installed")
