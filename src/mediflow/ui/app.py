"""
MediFlow — Sistema de Triagem, Extração e Roteamento de Documentos Clínicos.

Ponto de entrada da interface Streamlit. Executar com:

    streamlit run src/mediflow/ui/app.py

Este ficheiro só trata da configuração global, da barra lateral e da
navegação. Cada página vive em `views/` e a comunicação com a API
FastAPI está isolada em `api_client.py`.
"""

import streamlit as st

from pathlib import Path

from mediflow.ui import navigation
from mediflow.ui.api_client import check_api_health
from mediflow.ui.config import API_BASE_URL
from mediflow.ui.views import audit, dashboard, result, upload

ASSETS = Path(__file__).parent / "assets"

st.set_page_config(
    page_title="MediFlow · Triagem clínica",
    page_icon=str(ASSETS / "icon.svg"),
    layout="wide",
    initial_sidebar_state="expanded",
)
st.logo(str(ASSETS / "logo.svg"), icon_image=str(ASSETS / "icon.svg"), size="large")

# Valores iniciais de sessão (só definidos na primeira execução).
st.session_state.setdefault("api_url", API_BASE_URL)
st.session_state.setdefault("reviewer_name", "")

# --------------------------------------------------------------------------- #
# Páginas (agrupadas em secções na navegação lateral)
# --------------------------------------------------------------------------- #
navigation.PAGES.update({
    "dashboard": st.Page(dashboard.render, title="Visão geral", icon=":material/monitoring:",
                         url_path="dashboard", default=True),
    "upload": st.Page(upload.render, title="Enviar documento", icon=":material/upload_file:",
                      url_path="enviar"),
    "result": st.Page(result.render, title="Resultado da análise", icon=":material/clinical_notes:",
                      url_path="resultado"),
    "audit": st.Page(audit.render, title="Fila de auditoria", icon=":material/fact_check:",
                     url_path="auditoria"),
})
P = navigation.PAGES
page = st.navigation({
    "Operação": [P["dashboard"], P["upload"]],
    "Análise clínica": [P["result"], P["audit"]],
})

# --------------------------------------------------------------------------- #
# Barra lateral: ligação à API e identificação do revisor
# --------------------------------------------------------------------------- #
with st.sidebar:
    with st.container(border=True):
        st.text_input("URL da API", key="api_url", help="Endereço do servidor FastAPI.")
        with st.container(horizontal=True, vertical_alignment="center"):
            if mode := check_api_health(st.session_state["api_url"]):
                st.badge(f"API conectada · {mode}", icon=":material/cloud_done:", color="green")
            else:
                st.badge("API indisponível", icon=":material/cloud_off:", color="red")
            if st.button("Verificar", icon=":material/refresh:", type="tertiary"):
                check_api_health.clear()
                st.rerun()

    st.text_input("Revisor", key="reviewer_name", placeholder="Nome do operador",
                  icon=":material/badge:", help="Registrado em cada decisão de auditoria.")
    st.caption(":material/shield: As sugestões da IA requerem validação clínica.")

page.run()
