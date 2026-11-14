"""Página 4 — Fila de auditoria: revisão humana de documentos sinalizados.

Segue o visual da Visão geral (cartões, KPIs centrados, tabela com filtros).
À esquerda fica a fila; à direita, o documento selecionado e a decisão. Depois
de cada decisão a página avança sozinha para o documento seguinte da fila.
"""

from __future__ import annotations

from functools import partial

import pandas as pd
import streamlit as st

from mediflow.ui.api_client import APIError, get_backend
from mediflow.ui.components import (
    badge_row, card_styles, flag_label, format_confidence, mask_name, parse_ts,
    priority_badge, priority_label, show_api_error,
)
from mediflow.ui.config import DESTINATIONS, DOCUMENT_TYPES, PRIORITIES
from mediflow.ui.models import PRIORITY_TO_CONTRACT, normalize_document
from mediflow.ui.navigation import go_to
from mediflow.ui.text_metrics import centered_block_pad

PRIORITY_RANK = {"urgente": 0, "ambiguidade": 1, "rotina": 2}
PRIORITY_DOT = {"urgente": "🔴", "ambiguidade": "🟠", "rotina": "🟢"}
SORT_OPTIONS = ["Prioridade primeiro", "Mais antigos"]

# Larguras fixas das colunas (px); a última estica até à borda do cartão.
TABLE_WIDTHS = {"ID": 80, "Paciente": 100, "Prioridade": 125, "Motivo": 190, "Espera": 80, "Qualidade": 90}

# Chaves de sessão.
K_MASK, K_SEARCH, K_SORT = "audit_mask", "audit_search", "audit_sort"
K_PRIORITY, K_FLAGS = "audit_f_priority", "audit_f_flags"
K_TABLE_IDS, K_SELECTED, K_INCOMING = "_audit_table_ids", "audit_selected_id", "_audit_incoming"


# --------------------------------------------------------------------------- #
# Utilitários
# --------------------------------------------------------------------------- #
def _wait(ts: pd.Timestamp | None, now: pd.Timestamp) -> str:
    """Tempo de espera legível: '12 min', '3 h 20 min', '2 d'."""
    if ts is None:
        return "—"
    minutes = max(0, int((now - ts).total_seconds() // 60))
    if minutes < 60:
        return f"{minutes} min"
    if minutes < 24 * 60:
        h, m = divmod(minutes, 60)
        return f"{h} h {m:02d} min" if m else f"{h} h"
    return f"{minutes // (24 * 60)} d"


def _reason(doc: dict) -> str:
    """Primeira sinalização (a que justifica a revisão) e quantas mais existem."""
    if not doc["flags"]:
        return "—"
    extra = len(doc["flags"]) - 1
    return flag_label(doc["flags"][0]) + (f" +{extra}" if extra else "")


def _patient(doc: dict) -> str:
    name = doc["extracted"]["patient_name"]
    return mask_name(name) if st.session_state.get(K_MASK, True) else name


def _set_filter(priority: list[str] | None = None, flags: list[str] | None = None) -> None:
    st.session_state[K_PRIORITY] = priority or []
    st.session_state[K_FLAGS] = flags or []
    st.session_state[K_SEARCH] = ""


def _open(doc_id: str | None) -> None:
    """Abre um documento no painel de revisão (limpa filtros que o escondam)."""
    _set_filter()
    st.session_state[K_SELECTED] = doc_id


def _on_table_select(table_key: str) -> None:
    """Guarda o ID da linha escolhida (pela ordem que o utilizador viu)."""
    rows = st.session_state[table_key].selection.rows
    ids = st.session_state.get(K_TABLE_IDS, [])
    if rows and rows[0] < len(ids):
        st.session_state[K_SELECTED] = ids[rows[0]]


# --------------------------------------------------------------------------- #
# Blocos da página
# --------------------------------------------------------------------------- #
def _header(queue: list[dict], now: pd.Timestamp) -> None:
    with st.container(gap=None):
        with st.container(horizontal=True, vertical_alignment="center"):
            st.title("Fila de auditoria", anchor=False, width="stretch")
            st.caption(f"{len(queue)} documento(s) aguardando revisão", width="content")
        with st.container(horizontal=True, vertical_alignment="center"):
            st.caption("Valide as sugestões da IA nos documentos que a triagem não conseguiu fechar sozinha.",
                       width="stretch")
            st.caption(f"Atualizado às {now:%H:%M:%S}", width="content")
    st.space("small")
    with st.container(horizontal=True, horizontal_alignment="right"):
        st.toggle("Ocultar nomes", key=K_MASK, help="Mostra só o primeiro nome e as iniciais dos pacientes.")


def _kpi_card(key: str, label: str, icon: str, value, *, help_text: str, action: str, on_click) -> None:
    with st.container(border=True, height="stretch", gap="small", key=key, horizontal_alignment="center"):
        st.metric(label, value, help=help_text, icon=icon)
        st.space("stretch")
        st.button(action, key=f"btn_{key}", type="tertiary", icon=":material/filter_alt:", on_click=on_click)


def _kpis(queue: list[dict], now: pd.Timestamp) -> None:
    urgent = [d for d in queue if d["priority"] == "urgente"]
    low_conf = [d for d in queue if "baixa_confianca" in d["flags"]]
    dated = [d for d in queue if d["ts"] is not None]
    oldest = min(dated, key=lambda d: d["ts"]) if dated else None

    with st.container(horizontal=True, key="kpi_row"):
        _kpi_card("card_queue_total", "Na fila", ":material/pending_actions:", len(queue),
                  help_text="Documentos aguardando validação humana.",
                  action="Ver todos", on_click=_set_filter)
        _kpi_card("card_alert_urgent" if urgent else "card_kpi_urgent", "Possível urgência", ":material/e911_emergency:",
                  len(urgent), help_text="Documentos com marcador explícito de alerta: revise-os primeiro.",
                  action="Filtrar", on_click=lambda: _set_filter(priority=[priority_label("urgente")]))
        # No contrato v0.1 o indicador vem nulo (não calculado): sem valores, o cartão não diz nada.
        if any(d["confidence"] is not None for d in queue):
            _kpi_card("card_kpi_lowconf", "Qualidade baixa", ":material/neurology:", len(low_conf),
                      help_text="Indicador de completude e consistência abaixo do limite (não calibrado): "
                                "confirmar os campos com o original.",
                      action="Filtrar", on_click=lambda: _set_filter(flags=[flag_label("baixa_confianca")]))
        with st.container(border=True, height="stretch", gap="small", key="card_kpi_wait",
                          horizontal_alignment="center"):
            st.metric("Espera máxima", _wait(oldest["ts"], now) if oldest else "—", icon=":material/schedule:",
                      help="Há quanto tempo o documento mais antigo da fila aguarda revisão.")
            st.space("stretch")
            st.button("Revisar o mais antigo", key="btn_oldest", type="tertiary", icon=":material/arrow_forward:",
                      disabled=oldest is None, on_click=_open, args=(oldest["id"] if oldest else None,))


def _filtered(queue: list[dict]) -> list[dict]:
    """Aplica pesquisa e filtros e ordena (o critério da ordenação vem do controlo do cartão)."""
    q = st.session_state.get(K_SEARCH, "").strip().lower()
    prio = st.session_state.get(K_PRIORITY, [])
    flags = st.session_state.get(K_FLAGS, [])
    rows = [
        d for d in queue
        if (not prio or priority_label(d["priority"]) in prio)
        and (not flags or {flag_label(f) for f in d["flags"]} & set(flags))
        and (not q or q in " ".join(str(v) for v in (
            d["id"], d["extracted"]["patient_name"], d["extracted"]["document_type"], d["destination"],
        )).lower())
    ]
    rows.sort(key=lambda d: d["ts"] or pd.Timestamp.max)  # mais antigos primeiro
    if st.session_state.get(K_SORT) == "Prioridade primeiro":
        rows.sort(key=lambda d: PRIORITY_RANK.get(d["priority"], 3))  # estável: dentro da prioridade, por espera
    return rows


def _queue_card(queue: list[dict], now: pd.Timestamp) -> list[dict]:
    """Cartão com a fila; devolve os documentos visíveis (pela ordem mostrada)."""
    with st.container(border=True, height="stretch", key="card_queue_table"):
        with st.container(horizontal=True, vertical_alignment="bottom"):
            with st.container(gap=None):
                st.subheader("Documentos para revisar", anchor=False)
                st.caption("Selecione uma linha para revisá-la ao lado.")
            st.segmented_control("Ordenar", SORT_OPTIONS, key=K_SORT, required=True,
                                 label_visibility="collapsed")
        st.space("small")

        all_flags = sorted({flag_label(f) for d in queue for f in d["flags"]})
        with st.container(horizontal=True, vertical_alignment="center"):
            query = st.text_input("Pesquisar", key=K_SEARCH, icon=":material/search:",
                                  placeholder="Paciente, ID, tipo ou destino",
                                  label_visibility="collapsed", width="stretch")
            prio = st.multiselect("Prioridade", [s["label"] for s in PRIORITIES.values()], key=K_PRIORITY,
                                  placeholder="Prioridade", label_visibility="collapsed", width=200)
            flags = st.multiselect("Motivo", all_flags, key=K_FLAGS,
                                   placeholder="Motivo", label_visibility="collapsed", width=200)
            if query or prio or flags:
                st.button("Limpar", type="tertiary", on_click=_set_filter)

        rows = _filtered(queue)
        st.session_state[K_TABLE_IDS] = [d["id"] for d in rows]
        if not rows:
            st.info("Nenhum documento corresponde aos filtros.", icon=":material/search_off:")
            return rows

        df = pd.DataFrame([{
            "ID": d["id"],
            "Paciente": _patient(d),
            "Prioridade": f"{PRIORITY_DOT.get(d['priority'], '⚪')} {priority_label(d['priority'])}",
            "Motivo": _reason(d),
            "Espera": _wait(d["ts"], now),
            "Qualidade": format_confidence(d["confidence"]),
        } for d in rows])
        for col in df.columns:
            df[col] = centered_block_pad(df[col], TABLE_WIDTHS[col]) + df[col].astype(str)

        # A key muda com a lista e com o documento aberto: assim a linha destacada corresponde
        # sempre ao painel da direita (selection_default só vale no 1.º desenho de cada key).
        ids = [d["id"] for d in rows]
        selected = st.session_state.get(K_SELECTED)
        if selected not in ids:
            selected = st.session_state[K_SELECTED] = ids[0]
        table_key = f"audit_table_{abs(hash((tuple(ids), selected))) % 10**8}"
        st.dataframe(
            df, hide_index=True, key=table_key, on_select=partial(_on_table_select, table_key),
            selection_mode="single-row", row_height=35, height=(len(df) + 1) * 35 + 3,
            selection_default={"selection": {"rows": [ids.index(selected)]}} if selected in ids else None,
            alt="Documentos aguardando revisão",
            column_config={
                col: st.column_config.TextColumn(centered_block_pad([col], w) + col, width=w,
                                                 pinned=col == "ID" or None)
                for col, w in TABLE_WIDTHS.items()
            },
        )
        st.caption(f"{len(rows)} de {len(queue)} documento(s)")
        return rows


def _review_card(backend, doc: dict, next_id: str | None, now: pd.Timestamp) -> None:
    """Documento selecionado: porquê está na fila, campos editáveis e decisão."""
    ex = doc["extracted"]
    with st.container(border=True, height="stretch", key="card_review"):
        with st.container(horizontal=True, vertical_alignment="top"):
            with st.container(gap=None):
                st.subheader(f"{doc['id']} · {_patient(doc)}", anchor=False)
                received = f"{doc['ts']:%d/%m às %H:%M}" if doc["ts"] is not None else "—"
                st.caption(f"{ex['document_type']} · recebido {received} · aguardando há {_wait(doc['ts'], now)}")
            if st.button(":material/open_in_new:", key="btn_open_result", type="tertiary",
                         help="Abrir a análise completa"):
                go_to("result", doc_id=doc["id"])
        badge_row(priority_badge(doc["priority"]), f":gray-badge[:material/alt_route: {doc['destination']}]",
                  f":gray-badge[:material/neurology: Qualidade {format_confidence(doc['confidence'])}]"
                  if doc["confidence"] is not None else "")

        # Porquê está na fila: é a primeira coisa que o revisor precisa de saber.
        with st.container(border=True, gap="small", key="card_queue_reason"):
            st.markdown("**:material/flag: Por que precisa de revisão**")
            st.markdown("  \n".join(f"• {flag_label(f)}" for f in doc["flags"]) or "Sem sinalizações.")
            val = doc["validation"]
            fields = [*val["missing"], *val["illegible"], *val["conflicts"]]
            if fields:
                st.markdown(" ".join(f":orange-badge[{f}]" for f in fields))
            if doc["evidence"]["justification"]:
                st.caption(doc["evidence"]["justification"])
            rules = [r for r in doc["evidence"]["rules_fired"] if isinstance(r, dict)]
            if rules:
                with st.expander(f"Regras aplicadas ({len(rules)})", icon=":material/rule:"):
                    for rule in rules:
                        st.markdown(f"- :gray-badge[{rule.get('id', '—')}] **{rule.get('name', '')}** "
                                    f"→ {rule.get('effect', '')}")

        reviewer = st.session_state.get("reviewer_name", "").strip()
        with st.form(key=f"review_form_{doc['id']}", border=False):
            st.markdown("**Dados extraídos** · corrija o que estiver errado")
            c1, c2 = st.columns(2)
            # Campos não legíveis começam vazios: preenchê-los confirma o valor como legível.
            legible_name = ex["patient_name_status"] == "legivel"
            patient = c1.text_input("Paciente", ex["patient_name"] if legible_name else "",
                                    placeholder=ex["patient_name"])
            doctor = c2.text_input("Profissional", "" if ex["doctor_name"] == "—" else ex["doctor_name"])
            types = list(DOCUMENT_TYPES)
            doc_type = c1.selectbox("Categoria", types, format_func=lambda t: DOCUMENT_TYPES[t],
                                    index=types.index(ex["document_type_id"])
                                    if ex["document_type_id"] in types else types.index("outro_desconhecido"))
            destinations = list(DESTINATIONS)
            destination = c2.selectbox("Destino", destinations, format_func=lambda d: DESTINATIONS[d],
                                       index=destinations.index(doc["destination_id"])
                                       if doc["destination_id"] in destinations else destinations.index("auditoria_humana"))
            priority = st.segmented_control(
                "Prioridade documental", list(PRIORITIES), format_func=priority_label, required=True,
                default=doc["priority"] if doc["priority"] in PRIORITIES else "ambiguidade",
            )

            meds = [{"name": m["name"], "dosage": "" if m["dosage"].startswith("(") else m["dosage"]}
                    for m in ex["medications"]]
            meds_df = pd.DataFrame(meds or [{"name": "", "dosage": ""}])
            meds_df = meds_df.reindex(columns=["name", "dosage"]).fillna("")
            edited_meds = st.data_editor(
                meds_df, num_rows="dynamic", hide_index=True, alt="Medicamentos a corrigir",
                column_config={
                    "name": st.column_config.TextColumn("Medicamento"),
                    "dosage": st.column_config.TextColumn("Dosagem", help="Vazio = continua ilegível."),
                },
            )
            comment = st.text_area("Comentário", height=80,
                                   placeholder="Obrigatório para rejeitar. Ex.: dose confirmada com o prescritor.")

            if not reviewer:
                st.caption(":material/badge: Informe seu nome em **Revisor**, na barra lateral, para decidir.")
            with st.container(horizontal=True):
                reject = st.form_submit_button("Rejeitar", icon=":material/close:", disabled=not reviewer)
                st.space("stretch")
                approve = st.form_submit_button("Aprovar", type="primary", icon=":material/check:",
                                                disabled=not reviewer)

        if not (approve or reject):
            return
        if reject and not comment.strip():
            st.error("Para rejeitar, escreva o motivo no comentário.", icon=":material/edit_note:")
            return

        meds = [m for m in edited_meds.fillna("").to_dict("records") if str(m.get("name", "")).strip()]
        original_meds = [m for m in meds_df.to_dict("records") if str(m.get("name", "")).strip()]
        original_patient = ex["patient_name"] if legible_name else ""
        original_doctor = "" if ex["doctor_name"] == "—" else ex["doctor_name"]
        corrections = {}
        # Correções com os nomes de campos do contrato v0.1; só se envia o que mudou.
        if priority != doc["priority"]:
            corrections["classificacao"] = {"nivel_prioridade_documental": PRIORITY_TO_CONTRACT[priority]}
        if doc_type != ex["document_type_id"]:
            corrections.setdefault("classificacao", {})["tipo_documento"] = doc_type
        if destination != doc["destination_id"]:
            corrections["decisao_roteamento"] = {"destino_principal": destination}
        data = {}
        if patient.strip() != original_patient:
            data["paciente"] = ({"nome": patient.strip(), "nome_status": "legivel"} if patient.strip()
                                else {"nome": None, "nome_status": "ausente"})
        if doctor.strip() != original_doctor:
            data["profissional"] = {"nome": doctor.strip() or None}
        if meds != original_meds:
            data["medicamentos"] = [
                {"nome": str(m["name"]).strip(), "dosagem_texto": str(m["dosage"]).strip() or None,
                 "dosagem_status": "legivel" if str(m["dosage"]).strip() else "ilegivel"}
                for m in meds
            ]
        if data:
            corrections["dados_extraidos"] = data
        # Aprovar com campos alterados regista uma correção; sem alterações, uma aprovação simples.
        action = "rejeitar" if reject else "corrigir" if corrections else "aprovar"

        try:
            backend.submit_review(doc["id"], action, reviewer, comment.strip(), corrections)
        except APIError as err:
            show_api_error(err, "A revisão não foi registrada")
            return

        messages = {"aprovar": "aprovado", "corrigir": "aprovado com correções", "rejeitar": "rejeitado"}
        st.toast(f"Documento {doc['id']} {messages[action]}.", icon=":material/verified:")
        st.session_state[K_SELECTED] = next_id  # avança para o seguinte da fila
        st.session_state["selected_doc_id"] = None
        st.rerun()


def _empty_state() -> None:
    with st.container(border=True, horizontal_alignment="center", key="card_empty"):
        st.space("medium")
        st.markdown("### :material/task_alt: Fila em dia", text_alignment="center")
        st.caption("Não há documentos aguardando revisão humana.", text_alignment="center")
        st.space("medium")


# --------------------------------------------------------------------------- #
# Página
# --------------------------------------------------------------------------- #
def render() -> None:
    st.session_state.setdefault(K_SORT, SORT_OPTIONS[0])
    st.session_state.setdefault(K_MASK, True)  # privacidade por omissão, como na Visão geral
    card_styles()
    backend = get_backend()
    now = pd.Timestamp.now().floor("s")

    try:
        with st.spinner("Carregando a fila…"):
            queue = [{**d, "ts": parse_ts(d["received_at"])}
                     for d in map(normalize_document, backend.review_queue())]
    except APIError as err:
        if not err.not_implemented:
            show_api_error(err, "Não foi possível carregar a fila de auditoria")
            return
        # A API ainda não lista triagens: usa o último documento enviado, se aguardar revisão.
        st.caption(":material/info: A API ainda não lista triagens; mostrando o último documento enviado.")
        last = st.session_state.get("last_result")
        doc = normalize_document(last) if last else None
        queue = ([{**doc, "ts": parse_ts(doc["received_at"])}]
                 if doc and doc["status"] == "pending_review" and not doc["review"] else [])

    _header(queue, now)
    if not queue:
        _empty_state()
        return

    # Documento vindo de outra página (ex.: "Enviar para auditoria" no resultado): abre-o uma vez.
    incoming = st.session_state.get("selected_doc_id")
    if incoming != st.session_state.get(K_INCOMING):
        st.session_state[K_INCOMING] = incoming
        if incoming in {d["id"] for d in queue}:
            _set_filter()
            st.session_state[K_SELECTED] = incoming

    _kpis(queue, now)

    left, right = st.columns([11, 9], gap="medium")
    with left:
        rows = _queue_card(queue, now)

    ids = [d["id"] for d in rows]
    selected = st.session_state.get(K_SELECTED)

    with right:
        doc = next((d for d in rows if d["id"] == selected), None)
        if doc is None:
            with st.container(border=True, height="stretch", key="card_review_empty",
                              horizontal_alignment="center", vertical_alignment="center"):
                st.caption("Selecione um documento da fila para revisá-lo.", text_alignment="center")
            return
        i = ids.index(selected)
        next_id = ids[i + 1] if i + 1 < len(ids) else (ids[i - 1] if i > 0 else None)
        _review_card(backend, doc, next_id, now)
