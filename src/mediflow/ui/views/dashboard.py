"""Página 1 — Dashboard: visão geral do volume e estado dos documentos.

Tudo o que a página mostra (KPIs, gráficos, tabela) é calculado a partir da
lista de documentos e do período escolhido, para que os números batam sempre
entre si. O corpo corre num fragmento com atualização automática.
"""

from __future__ import annotations

from datetime import datetime
from functools import partial

import altair as alt
import pandas as pd
import streamlit as st

from mediflow.ui.api_client import APIError, get_backend
from mediflow.ui.components import (
    card_styles, mask_name, parse_ts, priority_label, show_api_error, status_label, surface,
)
from mediflow.ui.config import DASHBOARD_REFRESH, DONE_STATUSES, PRIORITIES, STATUSES
from mediflow.ui.models import normalize_document
from mediflow.ui.navigation import go_to
from mediflow.ui.text_metrics import centered_block_pad

# Períodos do seletor: rótulo -> duração ("today" = desde a meia-noite; None = todo o histórico).
PERIODS = {"Hoje": "today", "24 h": pd.Timedelta(hours=24), "7 dias": pd.Timedelta(days=7), "Tudo": None}
COMPARE_LABEL = {"Hoje": "ontem no mesmo horário", "24 h": "as 24 h anteriores", "7 dias": "os 7 dias anteriores"}

PRIORITY_RANK = {"urgente": 0, "ambiguidade": 1, "rotina": 2}
# Ponto colorido da prioridade na tabela (as etiquetas do grid não se deixam centrar).
PRIORITY_DOT = {"urgente": "🔴", "ambiguidade": "🟠", "rotina": "🟢"}
STATUS_DOT = {"received": "⚪", "processing": "⚪", "processed": "🟢", "pending_review": "🟣",
              "approved": "🔵", "corrected": "🟡",
              "rejected": "⚫", "error": "🔴"}
SORT_OPTIONS = ["Prioridade primeiro", "Mais recentes"]
PAGE_SIZE = 12  # documentos por página da tabela (setas para mudar de página)

# Larguras fixas das colunas da tabela (px): enchem a largura útil a 1440 px de ecrã
# (a última coluna estica até à borda, por isso "Qualidade" usa a largura real que fica).
TABLE_WIDTHS = {"ID": 80, "Recebido": 95, "Paciente": 95, "Tipo": 155, "Prioridade": 125,
                "Destino": 130, "Estado": 180, "Qualidade": 90}

WEEKDAYS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
          "setembro", "outubro", "novembro", "dezembro"]

# Chaves de sessão.
K_PERIOD, K_MASK, K_SEARCH, K_SORT = "dash_period", "dash_mask", "dash_search", "dash_sort"
K_PRIORITY, K_STATUS = "dash_f_priority", "dash_f_status"
K_TABLE, K_TABLE_IDS, K_SELECTED = "dash_table", "_dash_table_ids", "dash_selected_id"
K_PAGE, K_PAGE_FILTERS = "dash_page", "_dash_page_filters"
K_LAST_GOOD = "_dash_last_good"
K_SCROLL = "_dash_scroll_to_table"


# --------------------------------------------------------------------------- #
# Tempo
# --------------------------------------------------------------------------- #
def _windows(period: str, now: pd.Timestamp):
    """Devolve (início do período, início e fim do período anterior com a mesma duração)."""
    span = PERIODS[period]
    if span is None:
        return None, None, None
    start = now.normalize() if span == "today" else now - span
    prev_start = start - (pd.Timedelta(days=1) if span == "today" else span)
    return start, prev_start, prev_start + (now - start)


def _between(docs: list[dict], start, end) -> list[dict]:
    if start is None:
        return docs
    return [d for d in docs if d["ts"] is not None and start <= d["ts"] <= end]


def _bucket_freq(period: str) -> str:
    return "h" if period in ("Hoje", "24 h") else "D"


# --------------------------------------------------------------------------- #
# Dados
# --------------------------------------------------------------------------- #
def _load(backend, now: pd.Timestamp) -> tuple[list[dict], pd.Timestamp | None] | None:
    """Lê os documentos. Se a API falhar, recorre aos últimos dados bons (com aviso).

    Devolve (documentos, hora dos dados em cache) ou None se não houver nada para mostrar.
    """
    cache_key = f"{K_LAST_GOOD}:{st.session_state.get('api_url')}"
    try:
        with st.spinner("Carregando dados…"):
            raw = backend.list_documents()
        st.session_state[cache_key] = (raw, now)
        return raw, None
    except APIError as err:
        cached = st.session_state.get(cache_key)
        if cached is None and err.not_implemented:
            # A API ainda não lista triagens: mostra só o último documento enviado, se houver.
            st.caption(":material/info: A API ainda não lista triagens; mostrando o último documento enviado.")
            last = st.session_state.get("last_result")
            return ([last] if last else []), None
        if cached is None:
            show_api_error(err, "Não foi possível carregar o dashboard")
            return None
        return cached


# --------------------------------------------------------------------------- #
# Filtros da tabela (acionados pelos cartões)
# --------------------------------------------------------------------------- #
def _set_filter(priority: list[str] | None = None, status: list[str] | None = None) -> None:
    st.session_state[K_PRIORITY] = priority or []
    st.session_state[K_STATUS] = status or []
    st.session_state[K_SEARCH] = ""
    st.session_state[K_SCROLL] = True  # leva o utilizador até à tabela (feito no fim de _body)


def _clear_filters() -> None:
    _set_filter()


def _on_table_select(table_key: str) -> None:
    """Guarda o ID da linha escolhida com base na tabela que o utilizador viu.

    Assim, se a atualização automática reordenar as linhas, a ação continua a
    apontar para o documento certo.
    """
    rows = st.session_state[table_key].selection.rows
    ids = st.session_state.get(K_TABLE_IDS, [])
    st.session_state[K_SELECTED] = ids[rows[0]] if rows and rows[0] < len(ids) else None


def _go_to_page(page: int) -> None:
    st.session_state[K_PAGE] = page
    st.session_state[K_SELECTED] = None  # a seleção pertence à página que se deixou


# --------------------------------------------------------------------------- #
# Gráficos
# --------------------------------------------------------------------------- #
def _priority_frame(docs: list[dict]) -> pd.DataFrame:
    counts = pd.Series([d["priority"] for d in docs]).value_counts()
    keys = [*PRIORITIES, *[k for k in counts.index if k not in PRIORITIES]]
    return pd.DataFrame([
        {"key": k, "categoria": priority_label(k), "total": int(counts[k]),
         "cor": PRIORITIES.get(k, {}).get("color", "#94a3b8")}
        for k in keys if counts.get(k)
    ])


def _donut(df: pd.DataFrame) -> alt.LayerChart:
    """Anel fino com o total ao centro."""
    s = surface()
    size = 160
    # Centro fixo e sem padding: com o centro automático, o topo do anel ficava cortado.
    mid = {"x": alt.value(size / 2), "y": alt.value(size / 2)}
    ring = alt.Chart(df).mark_arc(innerRadius=54, outerRadius=74, cornerRadius=8, padAngle=0.03).encode(
        theta=alt.Theta("total:Q", stack=True),
        color=alt.Color("cor:N", scale=None),
        tooltip=[alt.Tooltip("categoria:N", title="Prioridade"), alt.Tooltip("total:Q", title="Documentos")],
        **mid,
    )
    center = alt.Chart(pd.DataFrame({"t": [str(int(df["total"].sum()))], "s": ["documentos"]}))
    number = center.mark_text(fontSize=28, fontWeight=800, color=s["text"], dy=-7).encode(text="t:N", **mid)
    caption = center.mark_text(fontSize=11, color=s["muted"], dy=16).encode(text="s:N", **mid)
    return (ring + number + caption).properties(width=size, height=size, padding=0).configure_view(
        strokeWidth=0).configure(background="transparent")


def _destinations(docs: list[dict]) -> alt.LayerChart | None:
    """Barras horizontais sobre um trilho: para onde foi encaminhado o volume do período."""
    counts = pd.Series([d["destination"] for d in docs]).value_counts()
    if counts.empty:
        return None
    df = counts.rename_axis("destino").reset_index(name="total")
    df["pct"] = df["total"] / df["total"].sum()
    df["rotulo"] = df["pct"].map(lambda p: f"{p:.0%}")
    df["max"] = df["total"].max()
    s = surface()

    order = df["destino"].tolist()  # value_counts já vem do maior para o menor
    # Nomes alinhados à esquerda: com labelAlign="left" o texto parte do ponto a labelPadding
    # do eixo, por isso labelPadding = largura da coluna de nomes (~7 px por carácter + folga).
    name_col = max(7 * int(df["destino"].str.len().max()), 60) + 16
    y = alt.Y("destino:N", sort=order, title=None,
              axis=alt.Axis(ticks=False, domain=False, labelLimit=170, labelPadding=name_col,
                            labelAlign="left", labelColor=s["text"], labelFontSize=12))
    x_scale = alt.Scale(domain=[0, float(df["total"].max()) * 1.2])
    # Tooltip só nas barras. O Streamlit liga-o por omissão em todas as marcas (o trilho e o
    # texto mostravam campos internos), por isso nessas camadas desliga-se explicitamente.
    no_tooltip = alt.value(None)
    track = alt.Chart(df).mark_bar(cornerRadius=6, height=10, color=s["track"]).encode(
        y=y, x=alt.X("max:Q", scale=x_scale, axis=None), tooltip=no_tooltip)
    bars = alt.Chart(df).mark_bar(cornerRadius=6, height=10, color=s["bar"]).encode(
        y=alt.Y("destino:N", sort=order), x=alt.X("total:Q", scale=x_scale, axis=None),
        tooltip=[alt.Tooltip("destino:N", title="Destino"), alt.Tooltip("total:Q", title="Documentos")])
    labels = alt.Chart(df).mark_text(align="left", dx=8, fontSize=12, fontWeight=600, color=s["muted"]).encode(
        y=alt.Y("destino:N", sort=order), x=alt.X("max:Q", scale=x_scale), text="rotulo:N", tooltip=no_tooltip)
    # Margem à esquerda: afasta os nomes da borda do cartão.
    padding = {"left": 16, "right": 5, "top": 5, "bottom": 5}
    return (track + bars + labels).properties(height=max(170, 32 * len(df)), padding=padding).configure_view(
        strokeWidth=0).configure(background="transparent")


# Grupos do gráfico de entrada (mesma lógica do KPI "Concluídos"): menos cores, leitura mais rápida.
TIMELINE_GROUPS = [
    ("Concluídos", DONE_STATUSES, STATUSES["processed"]["color"]),
    ("Pendentes de auditoria", ("pending_review",), STATUSES["pending_review"]["color"]),
    ("Rejeitados", ("rejected",), "#94a3b8"),
    ("Erros", ("error",), STATUSES["error"]["color"]),
]


def _timeline_frame(docs: list[dict], start: pd.Timestamp | None, now: pd.Timestamp,
                    period: str) -> pd.DataFrame | None:
    """Contagens por intervalo × grupo, com a grelha completa (intervalos sem documentos = 0).

    O eixo é contínuo e termina em "agora", para não misturar horas de dias diferentes.
    """
    group_of = {st_: label for label, statuses, _ in TIMELINE_GROUPS for st_ in statuses}
    rows = [(d["ts"], group_of.get(d["status"], "Outros")) for d in docs if d["ts"] is not None]
    if not rows:
        return None
    freq = _bucket_freq(period)
    df = pd.DataFrame(rows, columns=["ts", "grupo"])
    df["bucket"] = df["ts"].dt.floor(freq)
    first = start.floor(freq) if start is not None else df["bucket"].min()
    buckets = pd.date_range(first, now.floor(freq), freq=freq)
    groups = [g for g, _, _ in TIMELINE_GROUPS if g in set(df["grupo"])] + (
        ["Outros"] if "Outros" in set(df["grupo"]) else [])
    grid = pd.MultiIndex.from_product([buckets, groups], names=["bucket", "grupo"])
    return df.groupby(["bucket", "grupo"]).size().reindex(grid, fill_value=0).reset_index(name="total")


def _timeline(df: pd.DataFrame, period: str) -> alt.Chart:
    """Barras empilhadas finas, com separação entre segmentos e destaque da coluna sob o rato."""
    s = surface()
    hourly = _bucket_freq(period) == "h"
    unit = "yearmonthdatehours" if hourly else "yearmonthdate"
    colors = {g: c for g, _, c in TIMELINE_GROUPS} | {"Outros": "#cbd5e1"}
    domain = list(dict.fromkeys(df["grupo"]))
    df = df.assign(ordem=df["grupo"].map({g: i for i, g in enumerate(domain)}))

    hover = alt.selection_point(name="coluna", on="pointerover", clear="pointerout",
                                fields=["bucket"], empty=True)
    return (
        alt.Chart(df)
        .mark_bar(width={"band": 0.62}, cornerRadius=3, stroke=s["card"], strokeWidth=1.5)
        .encode(
            x=alt.X(f"{unit}(bucket):T", title=None,
                    axis=alt.Axis(format="%Hh" if hourly else "%d/%m", ticks=False, domain=False, grid=False,
                                  labelPadding=10, labelColor=s["muted"], labelFontSize=11,
                                  tickCount=8 if hourly else 7)),
            y=alt.Y("sum(total):Q", title=None, stack="zero",
                    axis=alt.Axis(tickCount=4, tickMinStep=1, ticks=False, domain=False, gridDash=[2, 4],
                                  gridColor=s["border"], labelColor=s["muted"], labelFontSize=11,
                                  labelPadding=8)),
            color=alt.Color("grupo:N", legend=None,
                            scale=alt.Scale(domain=domain, range=[colors[g] for g in domain])),
            order=alt.Order("ordem:Q"),
            opacity=alt.condition(hover, alt.value(1.0), alt.value(0.35)),
            tooltip=[alt.Tooltip(f"{unit}(bucket):T", title="Hora" if hourly else "Dia",
                                 format="%d/%m, %Hh" if hourly else "%d/%m/%Y"),
                     alt.Tooltip("grupo:N", title="Estado"),
                     alt.Tooltip("sum(total):Q", title="Documentos")],
        )
        .add_params(hover)
        .properties(height=240)
        .configure_view(strokeWidth=0)
        .configure(background="transparent")
    )


def _timeline_legend(df: pd.DataFrame) -> None:
    """Legenda própria (cor exata + total de cada grupo), alinhada com o título do cartão."""
    s = surface()
    colors = {g: c for g, _, c in TIMELINE_GROUPS} | {"Outros": "#cbd5e1"}
    totals = df.groupby("grupo", sort=False)["total"].sum()
    chips = "".join(
        f"<span style='display:inline-flex;align-items:center;gap:.45rem;margin-right:1.4rem;"
        f"font-size:.85rem;color:{s['muted']}'>"
        f"<span style='width:.6rem;height:.6rem;border-radius:3px;background:{colors[g]}'></span>"
        f"{g}<b style='color:{s['text']};font-weight:600'>{n}</b></span>"
        for g, n in totals.items()
    )
    st.html(f"<div style='display:flex;flex-wrap:wrap;row-gap:.4rem'>{chips}</div>")


# --------------------------------------------------------------------------- #
# Blocos da página
# --------------------------------------------------------------------------- #
def _styles() -> None:
    card_styles()
    st.html(f"""<style>
    /* Linhas da legenda sem quebra: o overflow auto do Streamlit mostrava uma barra de scroll em cada uma. */
    .st-key-priority_legend [data-testid='stHorizontalBlock'] {{ overflow: visible; }}
    /* Ícone da faixa de erros maior do que o texto (não há tamanho nativo intermédio). */
    .st-key-errors_icon span {{ font-size: 1.6rem !important; line-height: 1; }}
    /* Tooltips dos gráficos: "Rótulo: valor", uma linha por campo, alinhado à esquerda. */
    #vg-tooltip-element tr {{ display: block !important; white-space: nowrap; }}
    #vg-tooltip-element td {{ display: inline !important; padding: 0; text-align: left !important; }}
    #vg-tooltip-element td.key::after {{ content: ":"; }}
    #vg-tooltip-element td.value {{ padding-left: .3rem; }}
    </style>""")


def _header(updated_at: pd.Timestamp, stale: bool) -> str:
    today = updated_at
    # Duas linhas: título + data, e por baixo subtítulo + hora da atualização.
    with st.container(gap=None):
        with st.container(horizontal=True, vertical_alignment="center"):
            st.title("Visão geral", anchor=False, width="stretch")
            st.caption(f"{WEEKDAYS[today.weekday()].capitalize()}, {today.day} de {MONTHS[today.month - 1]}",
                       width="content")
        with st.container(horizontal=True, vertical_alignment="center"):
            st.caption("Triagem e roteamento de documentos clínicos.", width="stretch")
            if stale:
                st.badge(f"Sem conexão · dados de {updated_at:%H:%M}", icon=":material/cloud_off:", color="orange")
            else:
                st.caption(f"Atualizado às {updated_at:%H:%M:%S}", width="content")
    st.space("small")  # respiro entre o cabeçalho e os controlos

    with st.container(horizontal=True, vertical_alignment="center", gap="medium"):
        period = st.segmented_control("Período", list(PERIODS), key=K_PERIOD, required=True,
                                      label_visibility="collapsed")
        st.space("stretch")
        st.toggle("Ocultar nomes", key=K_MASK, help="Mostra só o primeiro nome e as iniciais dos pacientes.")
    return period


def _kpi_card(key: str, label: str, icon: str, value: int, *, delta=None, delta_color="normal",
              help_text: str, action: str, on_click=None, navigate: str | None = None) -> None:
    """Cartão de KPI; o botão filtra a tabela (`on_click`) ou abre outra página (`navigate`)."""
    with st.container(border=True, height="stretch", gap="small", key=key, horizontal_alignment="center"):
        st.metric(label, value, delta=delta, delta_color=delta_color, help=help_text, icon=icon)
        st.space("stretch")  # empurra o botão para o fundo do cartão
        if navigate:
            if st.button(action, key=f"btn_{key}", type="tertiary", icon=":material/arrow_forward:"):
                go_to(navigate)
        else:
            st.button(action, key=f"btn_{key}", type="tertiary", icon=":material/filter_alt:", on_click=on_click)


def _kpis(all_docs: list[dict], docs: list[dict], prev_docs: list[dict] | None, period: str) -> None:
    done = [d for d in docs if d["status"] in DONE_STATUSES]
    urgent = [d for d in docs if d["priority"] == "urgente"]
    # A fila de auditoria é o backlog completo, não só o que entrou no período.
    queue = [d for d in all_docs if d["status"] == "pending_review"]
    total = len(docs)
    # A seta de variação não tem texto ao lado; a ajuda (?) diz com que período compara.
    compare = f" A variação compara com {COMPARE_LABEL[period]}." if prev_docs is not None else ""

    def delta(cur: int, pred) -> int | None:
        return None if prev_docs is None else cur - sum(map(pred, prev_docs))

    with st.container(horizontal=True, key="kpi_row"):
        _kpi_card("card_kpi_total", "Recebidos", ":material/inbox:", total,
                  delta=delta(total, lambda d: True), delta_color="off",
                  help_text="Documentos que entraram no período escolhido." + compare,
                  action="Ver todos", on_click=_clear_filters)
        _kpi_card("card_kpi_done", "Concluídos", ":material/task_alt:", len(done),
                  delta=delta(len(done), lambda d: d["status"] in DONE_STATUSES),
                  help_text="Processados automaticamente, aprovados ou corrigidos em auditoria." + compare,
                  action="Filtrar",
                  on_click=lambda: _set_filter(status=[status_label(s) for s in DONE_STATUSES]))
        _kpi_card("card_alert_urgent" if urgent else "card_kpi_urgent", "Possível urgência", ":material/e911_emergency:",
                  len(urgent), delta=delta(len(urgent), lambda d: d["priority"] == "urgente"),
                  delta_color="inverse",
                  help_text="Documentos com marcador explícito de alerta (R001), encaminhados para a fila prioritária." + compare,
                  action="Filtrar", on_click=lambda: _set_filter(priority=[priority_label("urgente")]))
        _kpi_card("card_queue_pending" if queue else "card_kpi_pending", "Fila de auditoria", ":material/fact_check:",
                  len(queue), help_text="Documentos aguardando validação humana, de qualquer período.",
                  action="Abrir fila", navigate="audit")

    errors = [d for d in docs if d["status"] == "error"]
    if errors:
        with st.container(border=True, horizontal=True, vertical_alignment="center", key="card_alert_errors"):
            with st.container(width="content", key="errors_icon"):
                st.markdown(":red[:material/error:]")
            st.markdown(f"**{len(errors)} documento(s) com erro de processamento** "
                        "no período. Precisam de reenvio ou revisão manual.", width="stretch")
            st.button("Ver erros",
                      on_click=lambda: _set_filter(status=[status_label("error")]))


def _priority_card(docs: list[dict]) -> None:
    with st.container(border=True, height="stretch", key="card_priority"):
        with st.container(gap=None):  # título e legenda colados
            st.subheader("Por prioridade", anchor=False)
            st.caption("Classificação atribuída pela triagem")
        df = _priority_frame(docs)
        if df.empty:
            st.caption("Sem documentos neste período.")
            return
        total = int(df["total"].sum())
        # Anel + legenda num bloco com a largura do conteúdo, centrado no cartão
        # (os espaços elásticos centram-no também na vertical, abaixo do título).
        st.space("stretch")
        with st.container(horizontal=True, wrap=False, horizontal_alignment="center",
                          vertical_alignment="center", gap="small"):
            st.altair_chart(_donut(df), width="content", alt="Documentos por prioridade")
            with st.container(gap="small", width=172, key="priority_legend"):
                for _, row in df.iterrows():
                    badge = PRIORITIES.get(row["key"], {"badge": "gray"})["badge"]
                    with st.container(horizontal=True, wrap=False, vertical_alignment="center", gap="small"):
                        st.markdown(f":{badge}[●] {row['categoria']}", width="stretch")
                        # Largura fixa e texto centrado: os valores ficam alinhados em coluna.
                        st.markdown(f"**{row['total'] / total:.0%}**",
                                    width=50, text_alignment="center")
        st.space("stretch")


def _charts(docs: list[dict], start, now, period: str) -> None:
    left, right = st.columns([2, 3])
    with left:
        _priority_card(docs)
    with right.container(border=True, height="stretch", key="card_destination"):
        with st.container(gap=None):  # título e legenda colados
            st.subheader("Por destino", anchor=False)
            st.caption("Para onde a triagem encaminhou os documentos")
        chart = _destinations(docs)
        if chart is None:
            st.caption("Sem documentos neste período.")
        else:
            # Centrado na vertical, abaixo do título, como o anel do cartão "Por prioridade".
            st.space("stretch")
            st.altair_chart(chart, alt="Documentos por destino de encaminhamento")
            st.space("stretch")

    with st.container(border=True, key="card_timeline"):
        unit = "hora" if _bucket_freq(period) == "h" else "dia"
        df = _timeline_frame(docs, start, now, period)
        with st.container(gap=None):  # título e legenda colados
            st.subheader("Entrada de documentos", anchor=False)
            st.caption(f"Recebidos por {unit}, divididos pelo estado atual")
        st.space("small")  # respiro entre o subtítulo e a legenda
        if df is None:
            st.caption("Sem documentos neste período.")
            return
        _timeline_legend(df)
        st.altair_chart(_timeline(df, period), alt=f"Barras empilhadas de documentos recebidos por {unit}, por estado")


def _table(docs: list[dict]) -> None:
    with st.container(border=True, key="card_table"):
        with st.container(horizontal=True, vertical_alignment="bottom"):
            with st.container(gap=None):
                st.subheader("Documentos", anchor=False)
                st.caption("Selecione uma linha para abrir a análise detalhada.")
            st.segmented_control("Ordenar", SORT_OPTIONS, key=K_SORT, required=True,
                                 label_visibility="collapsed")
        st.space("small")  # respiro entre o subtítulo e os filtros

        with st.container(horizontal=True, vertical_alignment="center"):
            query = st.text_input("Pesquisar", key=K_SEARCH, icon=":material/search:",
                                  placeholder="Pesquisar paciente, ID, tipo ou destino",
                                  label_visibility="collapsed", width=460)
            prio = st.multiselect("Prioridade", [s["label"] for s in PRIORITIES.values()], key=K_PRIORITY,
                                  placeholder="Prioridade", label_visibility="collapsed", width=240)
            status = st.multiselect("Estado", [s["label"] for s in STATUSES.values()], key=K_STATUS,
                                    placeholder="Estado", label_visibility="collapsed", width=240)
            if query or prio or status:
                st.button("Limpar", type="tertiary", on_click=_clear_filters)

        q = query.strip().lower()
        rows = [
            d for d in docs
            if (not prio or priority_label(d["priority"]) in prio)
            and (not status or status_label(d["status"]) in status)
            and (not q or q in " ".join(str(v) for v in (
                d["id"], d["extracted"]["patient_name"], d["extracted"]["document_type"], d["destination"]
            )).lower())
        ]
        rows.sort(key=lambda d: d["ts"] or pd.Timestamp.min, reverse=True)
        if st.session_state.get(K_SORT) == "Prioridade primeiro":
            # Ordenação estável: dentro da mesma prioridade, pendentes primeiro e depois os mais recentes.
            rows.sort(key=lambda d: (PRIORITY_RANK.get(d["priority"], 3), d["status"] != "pending_review"))

        if not rows:
            st.info("Nenhum documento corresponde aos filtros.", icon=":material/search_off:")
            st.session_state[K_TABLE_IDS] = []
            return

        # Paginação: volta à 1.ª página quando o período, a pesquisa, os filtros ou a ordenação mudam
        # (a atualização automática não mexe na página em que o utilizador está).
        filters = (st.session_state.get(K_PERIOD), q, tuple(prio), tuple(status), st.session_state.get(K_SORT))
        if st.session_state.get(K_PAGE_FILTERS) != filters:
            st.session_state[K_PAGE_FILTERS] = filters
            st.session_state[K_PAGE] = 0
        pages = -(-len(rows) // PAGE_SIZE)
        page = min(st.session_state.get(K_PAGE, 0), pages - 1)
        first = page * PAGE_SIZE
        page_rows = rows[first:first + PAGE_SIZE]

        mask = st.session_state.get(K_MASK, True)
        # Todas as colunas como texto já formatado: assim cada uma pode ter o bloco de valores
        # centrado e alinhado à esquerda (a data e a confiança deixam de ser tipos nativos).
        df = pd.DataFrame([{
            "ID": d["id"],
            "Recebido": f"{d['ts']:%d/%m %H:%M}" if d["ts"] is not None else "—",
            "Paciente": mask_name(d["extracted"]["patient_name"]) if mask else d["extracted"]["patient_name"],
            "Tipo": d["extracted"]["document_type"],
            "Prioridade": f"{PRIORITY_DOT.get(d['priority'], '⚪')} {priority_label(d['priority'])}",
            "Destino": d["destination"],
            "Estado": f"{STATUS_DOT.get(d['status'], '⚪')} {status_label(d['status'])}",
            "Qualidade": f"{d['confidence']:.0%}" if d["confidence"] is not None else "—",
        } for d in page_rows])
        st.session_state[K_TABLE_IDS] = df["ID"].tolist()
        for col in df.columns:
            df[col] = centered_block_pad(df[col], TABLE_WIDTHS[col]) + df[col].astype(str)

        table_key = f"{K_TABLE}_{page}"  # uma tabela por página: a seleção não passa de uma para outra
        st.dataframe(
            df, hide_index=True, key=table_key, on_select=partial(_on_table_select, table_key),
            selection_mode="single-row", row_height=35, height=(len(df) + 1) * 35 + 3,
            alt="Documentos do período",
            column_config={
                col: st.column_config.TextColumn(_centered_header(col), width=width, pinned=col == "ID" or None)
                for col, width in TABLE_WIDTHS.items()
            },
        )

        with st.container(horizontal=True, vertical_alignment="center"):
            st.caption(f"{len(rows)} documento(s)", width="stretch")
            selected = next((d for d in page_rows if d["id"] == st.session_state.get(K_SELECTED)), None)
            if selected:
                name = selected["extracted"]["patient_name"]
                st.markdown(f":material/description: **{selected['id']}** · "
                            f"{mask_name(name) if mask else name} · {selected['extracted']['document_type']}")
                if st.button("Abrir análise", icon=":material/arrow_forward:", type="primary"):
                    go_to("result", doc_id=selected["id"])
            if pages > 1:
                st.button(":material/chevron_left:", key="page_prev", type="tertiary", help="Página anterior",
                          disabled=page == 0, on_click=_go_to_page, args=(page - 1,))
                st.caption(f"Página {page + 1} de {pages}", width="content")
                st.button(":material/chevron_right:", key="page_next", type="tertiary", help="Página seguinte",
                          disabled=page >= pages - 1, on_click=_go_to_page, args=(page + 1,))


def _centered_header(name: str) -> str:
    """Nome da coluna precedido dos espaços que o levam (aproximadamente) ao centro da coluna.

    O st.dataframe não deixa centrar só o cabeçalho (é desenhado num canvas, à esquerda).
    """
    return centered_block_pad([name], TABLE_WIDTHS[name]) + name


def _scroll_to_table() -> None:
    """Desliza a página até à tabela (o Streamlit não tem scroll programático nativo).

    O script espera que a tabela exista; o carimbo temporal força o browser a voltar a correr
    o script quando o mesmo botão é clicado outra vez.
    """
    st.html(
        f"""<script>/* {datetime.now().timestamp()} */
        (function go(n) {{
          const el = document.querySelector('.st-key-card_table');
          if (el) el.scrollIntoView({{behavior: 'smooth', block: 'start'}});
          else if (n < 30) setTimeout(() => go(n + 1), 100);
        }})(0);</script>""",
        unsafe_allow_javascript=True,
    )


def _empty_state() -> None:
    with st.container(border=True, horizontal_alignment="center", key="card_empty"):
        st.space("medium")
        st.markdown("### :material/inbox: Ainda não há documentos", text_alignment="center")
        st.space("medium")


# --------------------------------------------------------------------------- #
# Página
# --------------------------------------------------------------------------- #
def _body() -> None:
    now = pd.Timestamp.now().floor("s")
    loaded = _load(get_backend(), now)
    if loaded is None:
        return
    raw, stale_at = loaded

    all_docs = [{**doc, "ts": parse_ts(doc["received_at"])} for doc in map(normalize_document, raw)]
    period = _header(stale_at or now, stale=stale_at is not None)
    if stale_at is not None:
        st.warning("Não foi possível acessar a API. Estes são os últimos dados carregados com sucesso.",
                   icon=":material/cloud_off:")

    if not all_docs:
        _empty_state()
        return

    start, prev_start, prev_end = _windows(period, now)
    docs = _between(all_docs, start, now)
    # Só compara com o período anterior se o histórico o cobrir por inteiro (senão o delta engana).
    earliest = min((d["ts"] for d in all_docs if d["ts"] is not None), default=None)
    covered = prev_start is not None and earliest is not None and earliest <= prev_start
    prev_docs = _between(all_docs, prev_start, prev_end) if covered else None

    _kpis(all_docs, docs, prev_docs, period)
    _charts(docs, start, now, period)
    _table(docs)

    if st.session_state.pop(K_SCROLL, False):
        _scroll_to_table()


def render() -> None:
    st.session_state.setdefault(K_PERIOD, "24 h")
    st.session_state.setdefault(K_SORT, SORT_OPTIONS[0])
    st.session_state.setdefault(K_MASK, True)  # privacidade por omissão (ecrã pode estar à vista de terceiros)
    _styles()

    # O fragmento refaz-se sozinho; widgets lá dentro só reexecutam o próprio fragmento.
    st.fragment(_body, run_every=DASHBOARD_REFRESH)()
