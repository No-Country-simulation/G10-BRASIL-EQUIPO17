"""
Registo das páginas da aplicação.

`app.py` preenche `PAGES` a cada execução; as views usam `go_to("result")`
para navegar programaticamente sem importarem `app.py` (evita ciclos).
"""

import streamlit as st

PAGES: dict = {}


def go_to(key: str, doc_id: str | None = None) -> None:
    """Muda de página e, opcionalmente, seleciona um documento."""
    if doc_id:
        st.session_state["selected_doc_id"] = doc_id
    st.switch_page(PAGES[key])
