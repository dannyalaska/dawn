import requests
import streamlit as st

st.set_page_config(page_title="DAWN (dev)", layout="wide")
st.title("DAWN — dev")
st.caption("Streamlit is up. Next: API, Redis, and real features.")

st.subheader("Backend status")
try:
    api = "http://127.0.0.1:8000"
    r1 = requests.get(f"{api}/health", timeout=2).json()
    r2 = requests.get(f"{api}/health/redis", timeout=2).json()
    st.json({"health": r1, "redis": r2})
except Exception as e:
    st.warning(f"API not reachable: {e}")
