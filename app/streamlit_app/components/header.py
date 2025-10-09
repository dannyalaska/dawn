from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

import streamlit as st


def render_header(
    statuses: Iterable[Mapping[str, str]],
    *,
    logo_path: str | None = None,
) -> None:
    """Render the top header with logo, gradient title, and status lights."""
    st.markdown(_header_style_block(), unsafe_allow_html=True)

    left, right = st.columns([2, 5], vertical_alignment="center")
    with left:
        _render_branding(logo_path)
    with right:
        _render_status_lights(statuses)


def _render_branding(logo_path: str | None) -> None:
    if logo_path:
        image_path = Path(logo_path)
        if image_path.exists():
            st.image(str(image_path), width=64)
    st.markdown(
        """
        <div class="dawn-title-wrap">
            <span class="dawn-title">DAWN</span>
            <span class="dawn-subtitle">Local AI for Data Ops</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_status_lights(statuses: Iterable[Mapping[str, str]]) -> None:
    status_list = list(statuses)
    if not status_list:
        return
    cols = st.columns(len(status_list))
    for col, status in zip(cols, status_list, strict=False):
        label = status.get("label", "Service")
        state = status.get("state", "unknown").lower()
        tooltip = status.get("detail", "")
        col.markdown(
            f"""
            <div class="dawn-status-badge-wrap">
                <div class="dawn-status-badge" data-state="{state}">
                    <span class="dawn-status-dot"></span>
                    <span class="dawn-status-label">{label}</span>
                    <span class="dawn-status-tooltip">{tooltip}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _header_style_block() -> str:
    return """
    <style>
        .dawn-title-wrap {
            display: flex;
            flex-direction: column;
            gap: 0.2rem;
        }
        .dawn-title {
            font-size: 2rem;
            font-weight: 800;
            letter-spacing: 0.08em;
            font-family: 'Inter', 'Helvetica Neue', 'Segoe UI', sans-serif;
            background: linear-gradient(90deg, #ffb347, #ff7e5f 45%, #8a63ff 95%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .dawn-subtitle {
            font-size: 0.9rem;
            font-family: 'Inter', 'Helvetica Neue', 'Segoe UI', sans-serif;
            color: rgba(216, 221, 244, 0.78);
            text-transform: uppercase;
            letter-spacing: 0.12em;
        }
        .dawn-status-badge-wrap {
            display: flex;
            justify-content: flex-end;
        }
        .dawn-status-badge {
            position: relative;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 0.4rem;
            padding: 0.35rem 0.8rem;
            border-radius: 999px;
            background: linear-gradient(120deg, rgba(30, 36, 58, 0.75), rgba(39, 26, 62, 0.85));
            border: 1px solid rgba(142, 111, 255, 0.35);
            box-shadow: 0 10px 24px rgba(7, 9, 20, 0.55);
            transition: transform 0.25s ease, box-shadow 0.25s ease, border 0.25s ease;
        }
        .dawn-status-badge:hover {
            transform: translateY(-1px);
            box-shadow: 0 16px 36px rgba(10, 14, 32, 0.6);
            border-color: rgba(255, 150, 102, 0.6);
        }
        .dawn-status-dot {
            width: 10px;
            height: 10px;
            border-radius: 999px;
            background: #ffb347;
            box-shadow: 0 0 12px rgba(255, 179, 71, 0.85);
        }
        .dawn-status-badge[data-state="online"] .dawn-status-dot {
            background: #6fffc5;
            box-shadow: 0 0 12px rgba(111, 255, 197, 0.85);
        }
        .dawn-status-badge[data-state="degraded"] .dawn-status-dot {
            background: #ffd166;
            box-shadow: 0 0 12px rgba(255, 209, 102, 0.7);
        }
        .dawn-status-badge[data-state="offline"] .dawn-status-dot,
        .dawn-status-badge[data-state="error"] .dawn-status-dot {
            background: #ff6b6b;
            box-shadow: 0 0 12px rgba(255, 107, 107, 0.75);
        }
        .dawn-status-label {
            color: rgba(248, 249, 255, 0.92);
            font-weight: 600;
            font-size: 0.85rem;
            font-family: 'Inter', 'Helvetica Neue', 'Segoe UI', sans-serif;
        }
        .dawn-status-tooltip {
            position: absolute;
            left: 50%;
            top: calc(100% + 8px);
            transform: translateX(-50%);
            background: rgba(20, 16, 32, 0.95);
            color: rgba(226, 228, 245, 0.92);
            padding: 0.45rem 0.6rem;
            border-radius: 10px;
            border: 1px solid rgba(146, 120, 255, 0.35);
            min-width: 180px;
            text-align: center;
            font-size: 0.75rem;
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.2s ease;
            z-index: 20;
            box-shadow: 0 18px 32px rgba(9, 8, 18, 0.55);
        }
        .dawn-status-badge:hover .dawn-status-tooltip {
            opacity: 1;
        }
    </style>
    """
