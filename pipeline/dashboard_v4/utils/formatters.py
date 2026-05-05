"""
Formatting helper functions for Dashboard v4
"""
from .constants import JYO_MAP, KYAKU_MAP, BABA_MAP


def fmt_condition(cond: dict) -> str:
    """Format race condition dictionary to readable string."""
    parts = []
    if 'keibajo_code' in cond:
        parts.append(JYO_MAP.get(str(cond['keibajo_code']), cond['keibajo_code']))
    if 'kyakushitsu' in cond:
        parts.append(KYAKU_MAP.get(str(cond['kyakushitsu']), cond['kyakushitsu']))
    v = cond.get('baba_jotai', cond.get('baba', ''))
    if v != '':
        parts.append(BABA_MAP.get(str(v), str(v)))
    if 'dist_cat' in cond:
        parts.append(f"{cond['dist_cat']}m級")
    if 'grade_code' in cond:
        parts.append(f"G{cond['grade_code']}")
    if 'kishu' in cond:
        parts.append(str(cond['kishu']))
    if 'chichi' in cond:
        parts.append(f"父:{cond['chichi']}")
    return " / ".join(parts) if parts else str(cond)


def fmt_race(code: str) -> str:
    """Format race code (16-char) to readable format: MM/DD venue[0-9]R."""
    s = str(code).strip()
    if len(s) != 16:
        return s
    mm, dd = s[4:6], s[6:8]
    jyo = JYO_MAP.get(s[8:10], s[8:10])
    rno = s[14:16].lstrip('0') or '1'
    return f"{int(mm)}/{int(dd)} {jyo}{rno}R"


def fmt_percentage(value: float, decimals: int = 1) -> str:
    """Format float as percentage string."""
    return f"{value * 100:.{decimals}f}%"


def fmt_currency(value: float, decimals: int = 0) -> str:
    """Format float as currency (JPY)."""
    return f"{value:,.{int(decimals)}f}円" if decimals > 0 else f"{value:,.0f}円"


def fmt_odds(value: float, decimals: int = 1) -> str:
    """Format odds value."""
    return f"{value:.{decimals}f}倍"


def fmt_short_date(date_str: str) -> str:
    """Format date string to MM/DD format."""
    if not date_str or len(date_str) < 10:
        return date_str
    return date_str[5:7] + "/" + date_str[8:10]


def get_color_by_value(value: float, neutral: float = 0.0) -> str:
    """Get color code based on value performance (green if positive, red if negative)."""
    if value > neutral:
        return "#3fb950"
    elif value < neutral:
        return "#f85149"
    else:
        return "#e6edf3"
