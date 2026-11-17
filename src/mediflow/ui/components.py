"""
Componentes visuais reutilizáveis (cabeçalhos, badges, campos, erros).

Usa apenas elementos nativos do Streamlit (st.badge, st.metric, alertas com
título). O visual — cores, fontes, raios — vem de `.streamlit/config.toml`,
por isso funciona em modo claro e escuro e sobrevive a upgrades do Streamlit.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from mediflow.ui.api_client import APIError
from mediflow.ui.config import FLAG_LABELS, PRIORITIES, STATUSES

_FALLBACK = {"badge": "gray", "color": "#64748b", "icon": ":material/label:"}

# Superfícies dos cartões por tema. O tema do Streamlit só define uma borda global,
# por isso os cartões (containers com key "card_*") recebem estes estilos por CSS.
SURFACES = {
    "light": {
        "card": "#ffffff", "border": "#e6ebf1", "text": "#0f172a", "muted": "#64748b", "track": "#eef2f6",
        "shadow": "0 1px 2px rgba(15,23,42,.04), 0 8px 24px -12px rgba(15,23,42,.12)",
        "alert_bg": "#fff5f5", "alert_bd": "#fecaca", "queue_bg": "#f7f5ff", "queue_bd": "#ddd6fe",
        "bar": "#0d9488",
    },
    "dark": {
        "card": "#111a2e", "border": "#1e293b", "text": "#ffffff", "muted": "#94a3b8", "track": "#1a2540",
        "shadow": "0 1px 2px rgba(0,0,0,.3)",
        "alert_bg": "rgba(248,113,113,.08)", "alert_bd": "rgba(248,113,113,.35)",
        "queue_bg": "rgba(167,139,250,.08)", "queue_bd": "rgba(167,139,250,.35)",
        "bar": "#2dd4bf",
    },
}


def surface() -> dict:
    return SURFACES["dark" if st.context.theme.type == "dark" else "light"]


def card_styles() -> None:
    """Cartões (keys "card_*") e linha de KPIs centrados (key "kpi_row"), iguais em todas as páginas."""
    s = surface()
    st.html(f"""<style>
    [class*='st-key-card_'] {{
        background: {s['card']}; border: 1px solid {s['border']} !important;
        border-radius: 1.1rem !important; box-shadow: {s['shadow']};
    }}
    [class*='st-key-card_alert'] {{ background: {s['alert_bg']}; border-color: {s['alert_bd']} !important; }}
    [class*='st-key-card_queue'] {{ background: {s['queue_bg']}; border-color: {s['queue_bd']} !important; }}
    /* st.metric não tem alinhamento próprio: os cartões de KPI centram-se por CSS. */
    .st-key-kpi_row [data-testid='stMetric'],
    .st-key-kpi_row [data-testid='stMetric'] * {{ text-align: center; justify-content: center; }}
    .st-key-kpi_row [data-testid='stMetricLabel'] {{ display: flex; gap: .3rem; margin-bottom: .7rem; }}
    .st-key-kpi_row [data-testid='stMetricLabel'] > span {{ width: auto; flex: 0 0 auto; }}
    .st-key-kpi_row [data-testid='stMetricValue'] {{ margin-bottom: .7rem; }}
    </style>""")


# --------------------------------------------------------------------------- #
# Tempo e privacidade
# --------------------------------------------------------------------------- #
def parse_ts(value) -> pd.Timestamp | None:
    """Converte para hora local sem fuso (a API pode devolver datas com ou sem fuso)."""
    ts = pd.to_datetime(value, errors="coerce")
    if ts is None or pd.isna(ts):
        return None
    if ts.tzinfo is not None:
        ts = ts.tz_convert(datetime.now().astimezone().tzinfo).tz_localize(None)
    return ts


def mask_name(name: str) -> str:
    """'Ana Maria Ribeiro' -> 'Ana M. R.' (mantém o nome próprio para reconhecimento)."""
    parts = str(name).split()
    if len(parts) <= 1 or name == "—":
        return name
    return " ".join([parts[0]] + [f"{p[0]}." for p in parts[1:]])


# --------------------------------------------------------------------------- #
# Rótulos
# --------------------------------------------------------------------------- #
def priority_label(priority: str) -> str:
    return PRIORITIES.get(priority, {}).get("label", priority.title())


def status_label(status: str) -> str:
    return STATUSES.get(status, {}).get("label", status)


def flag_label(flag: str) -> str:
    return FLAG_LABELS.get(flag, flag.replace("_", " ").capitalize())


def format_confidence(value: float | None) -> str:
    return "—" if value is None else f"{value:.0%}"


# --------------------------------------------------------------------------- #
# Badges
# --------------------------------------------------------------------------- #
def _inline_badge(spec: dict, label: str) -> str:
    return f":{spec['badge']}-badge[{spec['icon']} {label}]"


def priority_badge(priority: str) -> str:
    """Badge em Markdown, para usar dentro de st.markdown / títulos."""
    return _inline_badge(PRIORITIES.get(priority, _FALLBACK), priority_label(priority))


def status_badge(status: str) -> str:
    return _inline_badge(STATUSES.get(status, _FALLBACK), status_label(status))


def pill_column(label: str, specs: dict, **kwargs):
    """Coluna de tabela que mostra cada valor como etiqueta colorida.

    As células devem conter listas de rótulos (ex.: ["Urgente"]).
    """
    return st.column_config.MultiselectColumn(
        label,
        options=[s["label"] for s in specs.values()],
        color=[s["color"] for s in specs.values()],
        **kwargs,
    )


def badge_row(*badges_md: str) -> None:
    """Linha de badges inline (prioridade, estado, sinalizações…)."""
    st.markdown(" ".join(b for b in badges_md if b))


# --------------------------------------------------------------------------- #
# Estrutura de página
# --------------------------------------------------------------------------- #
def page_header(title: str, subtitle: str = "", icon: str | None = None) -> None:
    with st.container(gap=None):  # subtítulo colado ao título, como na Visão geral
        st.title(title, icon=icon)
        if subtitle:
            st.caption(subtitle)
    st.space("small")  # respiro entre o cabeçalho e o conteúdo


def field(label: str, value) -> None:
    """Par chave/valor compacto (rótulo discreto, valor em destaque)."""
    st.caption(label)
    st.markdown(f"**{value or '—'}**")


def show_api_error(err: APIError, context: str = "") -> None:
    """Mostra um erro de API de forma amigável, com detalhe técnico recolhido."""
    st.error(err.message, title=context or "Erro de comunicação", icon=":material/cloud_off:")
    if err.detail:
        with st.expander("Detalhe técnico", icon=":material/code:"):
            st.code(str(err.detail))
    if err.status_code is None:
        st.caption("Dica: inicie a API na raiz do monorepo; veja `src/mediflow/ui/README.md`.")
