"""
KPI Card components for Dashboard v4
"""
import streamlit as st


def kpi_card(label: str, value: str, color: str = "#e6edf3", delta: str = "", width: str = None):
    """
    Display a KPI card with label, value, and optional delta.

    Args:
        label: KPI label text
        value: Main value to display
        color: Color for the value text
        delta: Optional delta/change text
        width: Optional CSS width string
    """
    style = f"width:{width};" if width else ""
    delta_html = f"<div class='kpi-delta'>{delta}</div>" if delta else ""

    st.markdown(f"""
<div class="kpi" style="{style}">
  <div class="kpi-sub">{label}</div>
  <div class="kpi-val" style="color:{color}">{value}</div>
  {delta_html}
</div>""", unsafe_allow_html=True)
