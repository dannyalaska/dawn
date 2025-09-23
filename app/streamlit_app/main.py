import requests
import streamlit as st

st.set_page_config(page_title="DAWN (dev)", layout="wide")
st.title("DAWN — dev")
st.caption("Streamlit is up. Next: API, Redis, and real features.")

# Backend health
st.subheader("Backend status")
try:
    api = "http://127.0.0.1:8000"
    r1 = requests.get(f"{api}/health", timeout=2).json()
    r2 = requests.get(f"{api}/health/redis", timeout=2).json()
    st.json({"health": r1, "redis": r2})
except Exception as e:
    st.warning(f"API not reachable: {e}")

st.divider()
st.subheader("Excel preview")

api = "http://127.0.0.1:8000"
up = st.file_uploader("Upload an Excel file (.xlsx, .xlsm, .xls)", type=["xlsx", "xlsm", "xls"])
sheet_name = st.text_input("Sheet name (optional)", value="")

if up and st.button("Generate preview"):
    files = {
        "file": (
            up.name,
            up.getvalue(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    params = {}
    if sheet_name.strip():
        params["sheet"] = sheet_name.strip()
    try:
        r = requests.post(f"{api}/ingest/preview", files=files, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        st.write(f"Sheet: **{data['sheet']}** — Shape: `{data['shape']}`")
        with st.expander("Columns profile", expanded=False):
            st.json(data["columns"])
        st.write("Rows (first 50):")
        st.dataframe(data["rows"])
    except Exception as exc:
        st.error(f"Preview failed: {exc}")


# Sidebar: recent uploads
with st.sidebar:
    st.header("Recent uploads")
    api_base = "http://127.0.0.1:8000"
    try:
        rec = requests.get(f"{api_base}/ingest/recent", timeout=5).json()
        if not rec:
            st.caption("No uploads yet.")
        else:
            # show compact table
            import pandas as _pd

            _df = _pd.DataFrame(rec)[["filename", "sheet", "rows", "cols", "uploaded_at", "sha16"]]
            st.dataframe(_df, use_container_width=True, height=240)
            pick = st.selectbox(
                "Replay a cached preview (by filename)",
                options=[f"{r['filename']} | {r['sheet'] or ''} | {r['sha16']}" for r in rec],
                index=0,
            )
            if st.button("Replay cached preview"):
                # parse selection to get sha16 + sheet
                sel = next(
                    r for r in rec if f"{r['filename']} | {r['sheet'] or ''} | {r['sha16']}" == pick
                )
                jj = requests.get(
                    f"{api_base}/ingest/preview_cached",
                    params={"sha16": sel["sha16"], "sheet": sel["sheet"]},
                    timeout=10,
                ).json()
                st.session_state["replayed"] = jj
    except Exception as _e:
        st.warning(f"Sidebar failed: {_e}")

# If we replayed, render under the main preview area
if "replayed" in st.session_state:
    st.divider()
    st.subheader("Replayed (from cache)")
    jj = st.session_state["replayed"]
    st.write(f"Sheet: **{jj['name']}** — Shape: `{tuple(jj['shape'])}`")
    with st.expander("Columns profile", expanded=False):
        st.json(jj["columns"])
    st.dataframe(jj["rows"])
