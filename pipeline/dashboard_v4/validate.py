"""
Validation script for Dashboard v4
Tests imports, data availability, and configuration
"""
import sys
import os
from pathlib import Path

BASE_PATH = Path(__file__).parent.parent.parent

def test_imports():
    """Test that all modules can be imported."""
    print("[OK] Testing imports...")
    errors = []

    try:
        from utils import constants, formatters, theme, data_loader
        print("      [OK] utils modules")
    except Exception as e:
        errors.append(f"utils import: {e}")

    try:
        from components import kpi_card
        print("      [OK] components")
    except Exception as e:
        errors.append(f"components import: {e}")

    try:
        from pages import home_page, performance_page, portfolio_page, backtest_page, analysis_page
        print("      [OK] all pages")
    except Exception as e:
        errors.append(f"pages import: {e}")

    return errors


def test_data_files():
    """Test that critical data files exist."""
    print("[OK] Checking data files...")
    errors = []
    data_dir = BASE_PATH / "data"

    required_files = [
        "bankroll.json",
        "roi_tracker.csv",
        "race_ranking_2026.csv",
    ]

    for fname in required_files:
        fpath = data_dir / fname
        if fpath.exists():
            print(f"      [OK] {fname}")
        else:
            errors.append(f"Missing: {fname}")

    return errors


def test_constants():
    """Test that constants are properly defined."""
    print("[OK] Testing constants...")
    errors = []

    try:
        from utils.constants import JYO_MAP, NAV_ITEMS, GRADE_COLORS
        if not JYO_MAP or len(JYO_MAP) == 0:
            errors.append("JYO_MAP is empty")
        if not NAV_ITEMS or len(NAV_ITEMS) < 5:
            errors.append(f"NAV_ITEMS has only {len(NAV_ITEMS)} items (expected 6)")
        print(f"      [OK] Constants loaded ({len(NAV_ITEMS)} nav items)")
    except Exception as e:
        errors.append(f"Constants: {e}")

    return errors


def main():
    """Run all validation tests."""
    os.chdir(BASE_PATH)
    sys.path.insert(0, str(BASE_PATH / "pipeline"))
    sys.path.insert(0, str(BASE_PATH / "pipeline" / "dashboard_v4"))

    print("\n" + "="*60)
    print("Dashboard v4 Validation")
    print("="*60)

    all_errors = []

    # Run tests
    all_errors.extend(test_imports())
    all_errors.extend(test_constants())
    all_errors.extend(test_data_files())

    # Report results
    print("\n" + "="*60)
    if all_errors:
        print(f"[FAIL] {len(all_errors)} ERRORS FOUND:")
        for err in all_errors:
            print(f"       - {err}")
        return 1
    else:
        print("[PASS] ALL VALIDATION CHECKS PASSED")
        print("\nTo start the dashboard:")
        print("      streamlit run pipeline/dashboard_v4/app.py")
        return 0


if __name__ == "__main__":
    sys.exit(main())
