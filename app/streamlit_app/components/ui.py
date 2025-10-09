from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import streamlit as st


@contextmanager
def styled_block(class_name: str) -> Iterator[None]:
    """
    Yield a Streamlit container and embed a hidden anchor marker that allows CSS
    to target the container itself (rather than relying on empty wrapper divs).
    """
    anchor_class = f"{class_name}-anchor"
    container = st.container()
    with container:
        st.markdown(
            f'<div class="dawn-block-anchor {anchor_class}"></div>',
            unsafe_allow_html=True,
        )
        yield
