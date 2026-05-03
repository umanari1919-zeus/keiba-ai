"""shutsuba_fetch の str+int エラーを特定するデバッグスクリプト"""
import traceback
import sys
sys.path.insert(0, "D:\\keiba_ai")

def test_each():
    from pipeline.shutsuba_fetch import (
        _build_master_features,
        _build_horse_history,
        _build_chokyo_features,
        _build_kishu_features,
        _build_kishu_keibajo_features,
        _build_chokyoshi_features,
        _build_prev_race_features,
    )

    steps = [
        ("_build_master_features",     _build_master_features),
        ("_build_horse_history",        _build_horse_history),
        ("_build_chokyo_features",      _build_chokyo_features),
        ("_build_kishu_features",       _build_kishu_features),
        ("_build_kishu_keibajo_features", _build_kishu_keibajo_features),
        ("_build_chokyoshi_features",   _build_chokyoshi_features),
        ("_build_prev_race_features",   _build_prev_race_features),
    ]

    for name, fn in steps:
        print(f"\n=== {name} ===")
        try:
            result = fn()
            print(f"  OK: {type(result).__name__}, shape={getattr(result, 'shape', 'N/A')}")
        except Exception as e:
            print(f"  ERROR: {type(e).__name__}: {e}")
            traceback.print_exc()

if __name__ == "__main__":
    test_each()
