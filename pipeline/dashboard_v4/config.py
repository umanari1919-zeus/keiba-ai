"""
Configuration for Dashboard v4
"""
import os
from datetime import datetime

# Paths
BASE_PATH = r"D:\keiba_ai"
PYTHON_EXE = r"C:\Users\uchih\AppData\Local\Programs\Python\Python313\python.exe"

# Runtime
YEAR = datetime.now().year
NOW = datetime.now()

# Page config
PAGE_CONFIG = {
    "page_title": "うまなり地蔵AI",
    "page_icon": "🏇",
    "layout": "wide",
    "initial_sidebar_state": "expanded",
}

# Streamlit display options
PANDAS_CONFIG = {
    "display.float_format": "{:,.2f}".format,
}

# Cache TTLs (seconds)
CACHE_TTL_SHORT = 60  # 1 minute - real-time data
CACHE_TTL_MEDIUM = 300  # 5 minutes - frequently updated
CACHE_TTL_LONG = 600  # 10 minutes - stable data

# Display settings
CHART_HEIGHT_SMALL = 280
CHART_HEIGHT_MEDIUM = 350
CHART_HEIGHT_LARGE = 450

# Colors
COLOR_POSITIVE = "#3fb950"
COLOR_NEGATIVE = "#f85149"
COLOR_NEUTRAL = "#e6edf3"
COLOR_WARNING = "#e3b341"
COLOR_INFO = "#58a6ff"
