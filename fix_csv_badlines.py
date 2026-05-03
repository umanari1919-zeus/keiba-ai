"""
keiba_data*.csv の read_csv に on_bad_lines='skip' を一括追加
"""
import re, pathlib

TARGET_FILES = [
    r"D:\keiba_ai\pipeline\feature_eng_02.py",
    r"D:\keiba_ai\pipeline\jockey_trainer_analysis_21.py",
    r"D:\keiba_ai\pipeline\statistical_tools_23.py",
    r"D:\keiba_ai\pipeline\portfolio_opt_11.py",
    r"D:\keiba_ai\pipeline\optuna_advanced_25.py",
    r"D:\keiba_ai\pipeline\nn_stacking_22.py",
    r"D:\keiba_ai\pipeline\pace_training_analysis_20.py",
    r"D:\keiba_ai\pipeline\feature_advanced_19.py",
    r"D:\keiba_ai\pipeline\nicks_analysis_18.py",
    r"D:\keiba_ai\pipeline\validation.py",
    r"D:\keiba_ai\pipeline\multi_bet_simulation.py",
]

# read_csv( ... keiba_data*.csv ... low_memory=False) に on_bad_lines='skip' を追加
# パターン: low_memory=False の後の ) の直前に追加
PATTERN = re.compile(
    r"""(pd\.read_csv\([^)]*keiba_data[^)]*?)(,?\s*low_memory=False)(\))""",
    re.DOTALL,
)

def fix_file(path: str) -> bool:
    text = pathlib.Path(path).read_text(encoding="utf-8")
    new_text, n = PATTERN.subn(
        lambda m: f"{m.group(1)}{m.group(2)}, on_bad_lines='skip'{m.group(3)}",
        text,
    )
    if n == 0:
        print(f"  スキップ（対象なし）: {path}")
        return False
    # すでに on_bad_lines がある場合は二重追加しない
    if "on_bad_lines" in new_text and new_text.count("on_bad_lines") > text.count("on_bad_lines") + n:
        print(f"  スキップ（既存あり）: {path}")
        return False
    pathlib.Path(path).write_text(new_text, encoding="utf-8")
    print(f"  OK fixed ({n}): {path}")
    return True

if __name__ == "__main__":
    for f in TARGET_FILES:
        fix_file(f)
    print("完了")
