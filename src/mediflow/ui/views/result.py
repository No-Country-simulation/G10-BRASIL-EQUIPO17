"""Página 3 — Resultado da análise: dados extraídos, prioridade, destino e evidências.

Segue o visual da Visão geral: cartões brancos com sombra (containers com key "card_*"),
KPIs centrados e cabeçalho com título + legenda. A página lê-se de cima para baixo:
qual o documento, o que a IA decidiu, porquê, e o que foi extraído.
"""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from mediflow.ui.api_client import APIError, get_backend
from mediflow.ui.components import (
    badge_row, flag_label, format_confidence, parse_ts, priority_label, show_api_error,
)
from mediflow.ui.config import LOW_CONFIDENCE_THRESHOLD, PRIORITIES
from mediflow.ui.models import normalize_document
from mediflow.ui.navigation import go_to
from mediflow.ui.text_metrics import centered_block_pad

# Severidade da regra -> (cor do badge, ícone, rótulo)
_SEVERITY = {
    "critical": ("red", ":material/error:", "Crítica"),
    "high": ("orange", ":material/warning:", "Alta"),
    "medium": ("blue", ":material/info:", "Média"),
    "info": ("green", ":material/check_circle:", "Informativa"),
}

# Superfícies dos cartões por tema (mesmos valores da Visão geral).
_SURFACES = {
    "light": {
        "card": "#ffffff", "border": "#e6ebf1",
        "shadow": "0 1px 2px rgba(15,23,42,.04), 0 8px 24px -12px rgba(15,23,42,.12)",
        "alert_bg": "#fff5f5", "alert_bd": "#fecaca", "warn_bg": "#fffbeb", "warn_bd": "#fde68a",
        "queue_bg": "#f7f5ff", "queue_bd": "#ddd6fe", "ok_bg": "#f0fdf4", "ok_bd": "#bbf7d0",
    },
    "dark": {
        "card": "#111a2e", "border": "#1e293b", "shadow": "0 1px 2px rgba(0,0,0,.3)",
        "alert_bg": "rgba(248,113,113,.08)", "alert_bd": "rgba(248,113,113,.35)",
        "warn_bg": "rgba(251,191,36,.07)", "warn_bd": "rgba(251,191,36,.3)",
        "queue_bg": "rgba(167,139,250,.08)", "queue_bd": "rgba(167,139,250,.35)",
        "ok_bg": "rgba(74,222,128,.07)", "ok_bd": "rgba(74,222,128,.3)",
    },
}

# Estado da consulta RAG quando não há fontes.
_RAG_STATUS = {"nao_consultado": "RAG não consultado.", "sem_resultados": "RAG consultado, sem resultados.",
               "falha": "A consulta ao RAG falhou."}

# Estado do armazenamento OCI -> (cor do badge, rótulo).
_STORAGE = {"pendente": ("gray", "Pendente"), "confirmado": ("green", "Confirmado"), "falha": ("red", "Falha")}

# Ação da revisão humana -> texto mostrado.
_REVIEW_ACTIONS = {"aprovar": "aprovado", "corrigir": "aprovado com correções", "rejeitar": "rejeitado"}

# Cartão do KPI de prioridade: tom de alerta para urgente, âmbar para ambiguidade.
_PRIORITY_CARD = {"urgente": "card_alert_priority", "ambiguidade": "card_warn_priority"}

# Larguras das colunas das tabelas (px), para centrar os cabeçalhos. Somam a largura útil
# dos cartões a 1440 px de ecrã (a última coluna estica até à borda).
TABLE_WIDTHS = {"Medicamento": 260, "Dosagem": 200, "Exame": 170, "Notas": 190}

# Chaves de sessão.
K_DOC = "result_doc"


# --------------------------------------------------------------------------- #
# Formatação
# --------------------------------------------------------------------------- #
def _fmt_datetime(value) -> str:
    """'2026-10-26T17:38' -> '26/10/2026 às 17:38' (texto original se não for uma data)."""
    ts = pd.to_datetime(value, errors="coerce")
    if value in (None, "", "—") or pd.isna(ts):
        return value or "—"
    return f"{ts:%d/%m/%Y às %H:%M}" if (ts.hour, ts.minute) != (0, 0) else f"{ts:%d/%m/%Y}"


# --------------------------------------------------------------------------- #
# Dados e seleção do documento
# --------------------------------------------------------------------------- #
def _load_document(backend, doc_id: str) -> dict | None:
    """Obtém o documento da API; recorre ao último resultado em sessão se necessário."""
    try:
        return backend.get_document(doc_id)
    except APIError as err:
        last = st.session_state.get("last_result")
        if last and normalize_document(last)["id"] == doc_id:
            return last
        show_api_error(err, f"Não foi possível carregar o documento {doc_id}")
        return None


def _select(doc_id: str) -> None:
    st.session_state[K_DOC] = doc_id
    st.session_state["selected_doc_id"] = doc_id


# --------------------------------------------------------------------------- #
# Blocos da página
# --------------------------------------------------------------------------- #
def _styles() -> None:
    s = _SURFACES["dark" if st.context.theme.type == "dark" else "light"]
    st.html(f"""<style>
    [class*='st-key-card_'] {{
        background: {s['card']}; border: 1px solid {s['border']} !important;
        border-radius: 1.1rem !important; box-shadow: {s['shadow']};
    }}
    [class*='st-key-card_alert'] {{ background: {s['alert_bg']}; border-color: {s['alert_bd']} !important; }}
    [class*='st-key-card_warn'] {{ background: {s['warn_bg']}; border-color: {s['warn_bd']} !important; }}
    [class*='st-key-card_queue'] {{ background: {s['queue_bg']}; border-color: {s['queue_bd']} !important; }}
    [class*='st-key-card_ok'] {{ background: {s['ok_bg']}; border-color: {s['ok_bd']} !important; }}
    /* KPIs centrados, como na Visão geral. */
    .st-key-kpi_row [data-testid='stMetric'],
    .st-key-kpi_row [data-testid='stMetric'] * {{ text-align: center; justify-content: center; }}
    .st-key-kpi_row [data-testid='stMetricLabel'] {{ display: flex; gap: .3rem; margin-bottom: .7rem; }}
    .st-key-kpi_row [data-testid='stMetricLabel'] > span {{ width: auto; flex: 0 0 auto; }}
    /* Ícones das faixas de aviso maiores do que o texto. */
    [class*='st-key-band_icon'] span {{ font-size: 1.6rem !important; line-height: 1; }}
    </style>""")


def _header(ids: list[str], labels: dict):
    """Título à esquerda; à direita, seletor do documento e espaço para as ações.

    Devolve (ID escolhido, container das ações), preenchido depois de carregar o documento.
    """
    with st.container(horizontal=True, vertical_alignment="bottom"):
        with st.container(gap=None):
            st.title("Resultado da análise", anchor=False)
            st.caption("O que a IA extraiu, para onde encaminhou e com que evidências.")
        actions = st.container(horizontal=True, vertical_alignment="center", gap="small", width="content")
        with actions:
            doc_id = st.selectbox("Documento", ids, key=K_DOC, format_func=lambda d: labels.get(d, d),
                                  label_visibility="collapsed", width=360,
                                  on_change=lambda: _select(st.session_state[K_DOC]))
    st.space("medium")  # respiro entre o cabeçalho e os KPIs
    return doc_id, actions


def _actions(doc: dict) -> None:
    if doc["status"] == "pending_review":
        if st.button("Revisar na fila", icon=":material/fact_check:", type="primary"):
            go_to("audit", doc_id=doc["id"])


def _kpis(doc: dict) -> None:
    """Decisão da IA: prioridade, destino e confiança."""
    p = PRIORITIES.get(doc["priority"], {"icon": ":material/label:"})
    conf = doc["confidence"]
    low = conf is not None and conf < LOW_CONFIDENCE_THRESHOLD
    threshold = f"{LOW_CONFIDENCE_THRESHOLD:.0%}"

    with st.container(horizontal=True, key="kpi_row"):
        with st.container(border=True, height="stretch", key=_PRIORITY_CARD.get(doc["priority"], "card_kpi_priority")):
            st.metric("Prioridade documental", priority_label(doc["priority"]), icon=p["icon"],
                      help="Atribuída pelo motor de regras. É um alerta documental, nunca um diagnóstico.")
        with st.container(border=True, height="stretch", key="card_kpi_destination"):
            st.metric("Destino", doc["destination"], icon=":material/alt_route:",
                      help="Fila para onde o documento foi encaminhado"
                           + (" (requer revisão humana)." if doc["requires_review"] else "."))
        with st.container(border=True, height="stretch", key="card_warn_confidence" if low else "card_kpi_confidence"):
            if conf is None:
                st.metric("Indicador de qualidade", "Não calculado", icon=":material/neurology:",
                          help="No contrato v0.1 o indicador ainda não é calculado (valor nulo). "
                               "Quando existir, não será uma probabilidade de acerto (calibrado = falso).")
            else:
                st.metric("Indicador de qualidade", format_confidence(conf), icon=":material/neurology:",
                          delta=f"Abaixo de {threshold}" if low else f"Acima de {threshold}",
                          delta_color="inverse" if low else "normal", delta_arrow="off",
                          help="Heurística de completude e consistência, não calibrada.")


def _flags(doc: dict) -> None:
    if not doc["flags"]:
        return
    # Um alerta clínico crítico pinta a faixa de vermelho; o resto fica em âmbar.
    critical = "alerta_critico" in doc["flags"]
    color = "red" if critical else "orange"
    with st.container(border=True, horizontal=True, vertical_alignment="center",
                      key="card_alert_flags" if critical else "card_warn_flags"):
        with st.container(width="content", key="band_icon_flags"):
            st.markdown(f":{color}[:material/flag:]")
        with st.container(gap=None):
            st.markdown("**Sinalizações do motor de regras**")
            st.caption("Pontos a confirmar antes de usar os dados extraídos.")
        badge_row(*(f":{'red' if f == 'alerta_critico' else 'orange'}-badge[{flag_label(f)}]"
                    for f in doc["flags"]))
    for alert in doc["alerts"]:
        if alert["message"]:
            st.caption(f":material/notifications: **{flag_label(alert['code'])}:** {alert['message']}")


def _review(doc: dict) -> None:
    r = doc["review"]
    if not r:
        return
    with st.container(border=True, horizontal=True, vertical_alignment="center", key="card_ok_review"):
        with st.container(width="content", key="band_icon_review"):
            st.markdown(":green[:material/verified:]")
        with st.container(gap=None):
            action = _REVIEW_ACTIONS.get(r.get("action"), r.get("action") or "—")
            st.markdown(f"**Revisado por {r.get('reviewer') or '—'}** · {action}")
            st.caption(f"{_fmt_datetime(r.get('reviewed_at'))}"
                       + (f" · {r['comment']}" if r.get("comment") else ""))


def _card_title(title: str, caption: str) -> None:
    with st.container(gap=None):  # título e legenda colados
        st.subheader(title, anchor=False)
        st.caption(caption)


def _field(label: str, value) -> None:
    """Rótulo discreto colado ao valor."""
    with st.container(gap=None):
        st.caption(label)
        st.markdown(f"**{value or '—'}**")


def _empty(text: str, icon: str) -> None:
    st.space("stretch")
    st.caption(f"{icon} {text}", text_alignment="center")
    st.space("stretch")


def _centered(df: pd.DataFrame) -> dict:
    """Centra valores e cabeçalhos de todas as colunas da tabela.

    O st.dataframe só alinha as células; o cabeçalho é desenhado à esquerda num canvas, por
    isso leva à frente os espaços que o centram numa coluna de largura fixa (como na Visão geral).
    """
    config = {}
    for col in df.columns:
        width = TABLE_WIDTHS.get(col)
        label = centered_block_pad([col], width) + col if width else col
        if col == "Confiança":
            config[col] = st.column_config.NumberColumn(label, width=width, format="percent", alignment="center")
        else:
            config[col] = st.column_config.Column(label, width=width, alignment="center")
    return config


def _extracted_tab(doc: dict) -> None:
    ex = doc["extracted"]
    blocks = [
        ("Paciente", "Identificação do paciente",
         [("Nome", ex["patient_name"]), ("Identificador", ex["patient_id"]),
          ("Idade", f"{ex['patient_age']} anos" if ex["patient_age"] is not None else "—")]),
        ("Profissional", "Transcrito do documento, sem validação",
         [("Nome", ex["doctor_name"]), ("CRM", ex["doctor_license"])]),
        ("Documento", "Categoria e especialidade",
         [("Tipo", ex["document_type"]), ("Especialidade", ex["specialty"])]),
    ]
    with st.container(horizontal=True):
        for i, (title, caption, fields) in enumerate(blocks):
            with st.container(border=True, height="stretch", key=f"card_info_{i}"):
                _card_title(title, caption)
                with st.container(horizontal=True):
                    for label, value in fields:
                        _field(label, value)

    refs = {label: value for label, value in ex["references"].items() if value}
    with st.container(border=True, key="card_references"):
        _card_title("Datas e referências", "Só o que está escrito no documento; o CID nunca é sugerido")
        if refs:
            with st.container(horizontal=True):
                for label, value in refs.items():
                    _field(label, _fmt_datetime(value) if label not in ("Afastamento", "Guia", "CID documentado")
                           else value)
        else:
            st.caption("Nenhuma data, guia ou CID identificado no documento.")

    if ex["notes"]:
        with st.container(border=True, key="card_notes"):
            _card_title("Resumo", "Texto livre identificado no documento")
            st.markdown(ex["notes"])

    left, right = st.columns([3, 2])
    with left.container(border=True, height="stretch", key="card_medications"):
        n = len(ex["medications"])
        _card_title("Medicamentos", f"{n} identificado(s)" if n else "Prescrição extraída")
        if ex["medications"]:
            df = pd.DataFrame(ex["medications"]).rename(columns={"name": "Medicamento", "dosage": "Dosagem"})
            st.dataframe(df, hide_index=True, column_config=_centered(df), alt="Medicamentos extraídos")
        else:
            _empty("Nenhum medicamento identificado.", ":material/medication:")
    with right.container(border=True, height="stretch", key="card_exams"):
        n = len(ex["exams"])
        _card_title("Exames e procedimentos", f"{n} identificado(s)" if n else "Exames, resultados e pedidos")
        if ex["exams"]:
            df = pd.DataFrame(ex["exams"]).rename(columns={"name": "Exame", "notes": "Notas"})
            st.dataframe(df, hide_index=True, column_config=_centered(df), alt="Exames extraídos")
        else:
            _empty("Nenhum exame identificado.", ":material/biotech:")


def _evidence_tab(doc: dict) -> None:
    ev = doc["evidence"]

    with st.container(border=True, key="card_justification"):
        _card_title("Por que esta decisão", "Justificativa da regra principal")
        st.markdown(ev["justification"] or ":gray[A API não retornou justificativa.]")

    left, right = st.columns(2)
    with left.container(border=True, height="stretch", key="card_doc_evidence"):
        _card_title("Trechos do documento", "Evidência literal de cada campo extraído")
        if not ev["document"]:
            _empty("Nenhum trecho registrado.", ":material/format_quote:")
        for e in ev["document"]:
            with st.container(gap=None):
                page = f" · pág. {e['page']}" if e.get("page") else ""
                st.caption(f"`{e['field']}`{page}")
                st.markdown(f"*«{e['excerpt']}»*")
    with right.container(border=True, height="stretch", key="card_validation"):
        val = doc["validation"]
        _card_title("Validação", f"Integridade documental: {val['integrity']}")
        groups = [("Ausentes", val["missing"], "orange"), ("Ilegíveis", val["illegible"], "orange"),
                  ("Conflitantes", val["conflicts"], "red")]
        if not any(fields for _, fields, _ in groups):
            _empty("Nenhum campo ausente, ilegível ou conflitante.", ":material/check_circle:")
        for label, fields, color in groups:
            if fields:
                st.markdown(f"**{label}**  \n" + " ".join(f":{color}-badge[{f}]" for f in fields))
        for note in val["notes"]:
            st.caption(note)

    left, right = st.columns(2)
    with left.container(border=True, height="stretch", key="card_rules"):
        _card_title("Regras disparadas", "Regras administrativas v0.1 (rules/roteamento.yaml)")
        if not ev["rules_fired"]:
            _empty("Nenhuma regra disparada.", ":material/rule:")
        for rule in ev["rules_fired"]:
            rule = rule if isinstance(rule, dict) else {"name": str(rule)}
            sev = str(rule.get("severity", "")).lower()
            color, icon, sev_label = _SEVERITY.get(sev, ("gray", ":material/rule:", sev or ""))
            with st.container(gap=None):
                with st.container(horizontal=True, vertical_alignment="center", gap="small"):
                    st.markdown(f":{color}[{icon}] **{rule.get('name', 'Regra')}**", width="stretch")
                    badge_row(f":gray-badge[{rule.get('id', '—')}]",
                              ":primary-badge[Principal]" if rule.get("main") else "",
                              f":{color}-badge[{sev_label}]" if sev_label else "")
                if rule.get("description"):
                    st.caption(rule["description"])
                if rule.get("effect"):
                    st.markdown(f":primary[:material/arrow_forward: {rule['effect']}]")

    with right.container(border=True, height="stretch", key="card_sources"):
        _card_title("Fontes citadas", "Recuperadas pelo RAG; não decidem a rota")
        if not ev["sources"]:
            _empty(_RAG_STATUS.get(ev["rag_status"], "Nenhuma fonte recuperada."), ":material/menu_book:")
        for i, src in enumerate(ev["sources"], start=1):
            src = src if isinstance(src, dict) else {"title": str(src)}
            with st.container(gap=None):
                with st.container(horizontal=True, vertical_alignment="center", gap="small"):
                    st.markdown(f"**{i}. {src.get('title', 'Fonte')}**", width="stretch")
                    if src.get("score") is not None:
                        st.badge(f"Relevância {format_confidence(src['score'])}", color="primary")
                if src.get("excerpt"):
                    st.markdown(f"*«{src['excerpt']}»*")
                if src.get("ref"):
                    version = f" · versão {src['version']}" if src.get("version") else ""
                    st.caption(f":material/link: `{src['ref']}`{version}")


def _trace_tab(doc: dict) -> None:
    """Entrada, versões, armazenamento OCI e eventos: de onde veio o resultado e onde ficou."""
    tr = doc["trace"]
    storage = tr["storage"]
    status = storage.get("status") or "pendente"
    color, label = _STORAGE.get(status, ("gray", status))

    left, right = st.columns(2)
    with left.container(border=True, height="stretch", key="card_trace_input"):
        _card_title("Entrada", "Como o documento chegou ao MediFlow")
        with st.container(horizontal=True):
            _field("Tipo", tr["input_type"].upper())
            _field("Canal", doc["channel"])
            _field("Arquivo", doc["filename"])
        with st.container(horizontal=True):
            _field("Contrato", tr["contract_version"])
            _field("Regras", tr["rules_version"])
            _field("Indicador", "não calculado" if tr["quality_method"] == "nao_calculado" else tr["quality_method"])
        st.caption("SHA-256")
        st.code(tr["sha256"] or "não apurado", language=None)
    with right.container(border=True, height="stretch", key="card_trace_storage"):
        with st.container(horizontal=True, vertical_alignment="center"):
            _card_title("Armazenamento OCI", "Original, resultado e histórico")
            st.badge(label, color=color)
        if status == "confirmado":
            _field("Bucket", storage.get("bucket"))
            for key, name in (("chave_original", "Original"), ("chave_resultado", "Resultado"),
                              ("chave_historico", "Histórico")):
                st.caption(name)
                st.code(storage.get(key) or "—", language=None)
        else:
            _empty("Endereços só aparecem depois de a gravação ser confirmada.", ":material/cloud_upload:")

    with st.container(border=True, key="card_trace_events"):
        _card_title("Eventos", "Histórico de processamento registrado pela API")
        if tr["events"]:
            df = pd.DataFrame([{
                "Quando": _fmt_datetime(parse_ts(e["timestamp"])) if e["timestamp"] else "—",
                "Evento": e["code"], "Descrição": e["description"],
            } for e in tr["events"]])
            st.dataframe(df, hide_index=True, alt="Eventos de processamento")
        else:
            st.caption("A API não registrou eventos para este documento.")


def _empty_state() -> None:
    with st.container(border=True, horizontal_alignment="center", key="card_empty"):
        st.space("medium")
        st.markdown("### :material/inbox: Ainda não há documentos analisados", text_alignment="center")
        st.space("medium")


# --------------------------------------------------------------------------- #
# Página
# --------------------------------------------------------------------------- #
def render() -> None:
    _styles()
    backend = get_backend()

    try:
        documents = [normalize_document(d) for d in backend.list_documents()]
    except APIError as err:
        if err.not_implemented:
            st.caption(":material/info: A API ainda não lista triagens; mostrando o último documento enviado.")
        else:
            show_api_error(err, "Não foi possível obter a lista de documentos")
        documents = []

    ids = [d["id"] for d in documents]
    selected = st.session_state.get("selected_doc_id")
    if selected and selected not in ids:
        ids.insert(0, selected)  # documento recém-processado ainda não listado
    if not ids:
        with st.container(gap=None):
            st.title("Resultado da análise", anchor=False)
            st.caption("O que a IA extraiu, para onde encaminhou e com que evidências.")
        st.space("small")
        _empty_state()
        return

    # O documento vindo de outra página (go_to) tem prioridade sobre a última escolha do seletor.
    if selected in ids:
        st.session_state[K_DOC] = selected
    elif st.session_state.get(K_DOC) not in ids:
        st.session_state[K_DOC] = ids[0]

    labels = {d["id"]: f"{d['id']} · {d['extracted']['patient_name']}" for d in documents}
    doc_id, actions = _header(ids, labels)
    st.session_state["selected_doc_id"] = doc_id

    raw = _load_document(backend, doc_id)
    if raw is None:
        return
    doc = normalize_document(raw)

    with actions:
        _actions(doc)
    _kpis(doc)
    _flags(doc)
    _review(doc)

    st.space("small")
    tab_data, tab_ev, tab_trace, tab_json = st.tabs([
        ":material/description: Dados extraídos",
        ":material/fact_check: Evidências",
        ":material/history: Rastreabilidade",
        ":material/data_object: JSON",
    ])
    with tab_data:
        _extracted_tab(doc)
    with tab_ev:
        _evidence_tab(doc)
    with tab_trace:
        _trace_tab(doc)
    with tab_json:
        with st.container(border=True, key="card_json"):
            with st.container(horizontal=True, vertical_alignment="center"):
                _card_title("Resposta da API", "Documento completo, exatamente como retornado pelo back-end")
                st.download_button("Exportar JSON", json.dumps(doc["raw"], ensure_ascii=False, indent=2),
                                   file_name=f"{doc['id']}.json", mime="application/json",
                                   icon=":material/download:")
            st.json(doc["raw"], expanded=2)
