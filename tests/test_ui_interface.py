"""Testes offline da interface Streamlit (sem servidor, Gemini ou OCI).

Cobrem normalização do ResultadoTriagem v0.1, horários (API x interface),
filtros temporais da Visão geral, API indisponível/não implementada, fila de
auditoria com dados da sessão e ausência de confiança artificial.
"""
from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pandas as pd
import pytest
import requests
import streamlit as st

from mediflow.ui import api_client
from mediflow.ui.api_client import UI_RECEIVED_KEY, APIError, MediFlowClient
from mediflow.ui.components import parse_ts, received_label
from mediflow.ui.models import normalize_document
from mediflow.ui.views.dashboard import _between, _windows

RAIZ = Path(__file__).resolve().parents[1]
BASE = "http://api-teste.local"


def exemplo(doc_id: str) -> dict:
    return json.loads((RAIZ / "exemplos" / f"{doc_id}_resultado.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def sessao_limpa():
    st.session_state.clear()
    st.session_state["api_url"] = BASE
    yield
    st.session_state.clear()


class Resposta:
    def __init__(self, status: int, corpo=None):
        self.status_code = status
        self.ok = 200 <= status < 300
        self._corpo = corpo
        self.content = b"" if corpo is None else json.dumps(corpo).encode()
        self.text = self.content.decode()

    def json(self):
        if self._corpo is None:
            raise ValueError("sem corpo")
        return self._corpo


def api_falsa(monkeypatch, rotas: dict):
    """rotas: {(método, sufixo_da_url): Resposta | Exception}."""
    chamadas = []

    def request(method, url, **kwargs):
        chamadas.append((method, url))
        for (m, sufixo), resposta in rotas.items():
            if m == method and url.endswith(sufixo):
                if isinstance(resposta, Exception):
                    raise resposta
                return resposta
        return Resposta(404, {"detail": {"mensagem": "rota inexistente"}})

    monkeypatch.setattr(requests, "request", request)
    return chamadas


# --------------------------------------------------------------------------- #
# Normalização dos três cenários
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("doc_id,status,prioridade,destino", [
    ("DOC-001", "processed", "rotina", "prontuario_documental"),
    ("DOC-002", "pending_review", "urgente", "fila_prioritaria_avaliacao_humana"),
    ("DOC-005", "pending_review", "ambiguidade", "auditoria_humana"),
])
def test_normaliza_tres_cenarios(doc_id, status, prioridade, destino):
    doc = normalize_document(exemplo(doc_id))
    assert doc["id"] == doc_id
    assert doc["status"] == status
    assert doc["priority"] == prioridade
    assert doc["destination_id"] == destino


def test_dosagem_ilegivel_do_doc005_preservada():
    doc = normalize_document(exemplo("DOC-005"))
    assert doc["extracted"]["medications"][0]["dosage"].startswith("(ileg")
    assert "dosagem_ilegivel" in doc["flags"]
    bruto = exemplo("DOC-005")
    assert bruto["dados_extraidos"]["medicamentos"][0]["dosagem_texto"] is None


@pytest.mark.parametrize("doc_id", ["DOC-001", "DOC-002", "DOC-005"])
def test_indicador_nao_calculado_nao_vira_valor_artificial(doc_id):
    doc = normalize_document(exemplo(doc_id))
    assert doc["confidence"] is None
    assert "baixa_confianca" not in doc["flags"]
    assert received_label({**doc, "ts": None}) == "—"


def test_resultado_vazio_nao_quebra():
    doc = normalize_document(None)
    assert doc["id"] == "—" and doc["received_at"] is None and doc["received_at_source"] is None


# --------------------------------------------------------------------------- #
# Horários: API x interface, fusos
# --------------------------------------------------------------------------- #
def test_sem_horario_algum():
    doc = normalize_document(exemplo("DOC-001"))
    assert (doc["received_at"], doc["received_at_source"]) == (None, None)


def test_horario_da_api_tem_precedencia_sobre_o_da_interface():
    bruto = {**exemplo("DOC-001"), "recebido_em": "2026-11-17T12:00:00Z", UI_RECEIVED_KEY: "2026-11-17T13:00:00Z"}
    doc = normalize_document(bruto)
    assert doc["received_at"] == "2026-11-17T12:00:00Z"
    assert doc["received_at_source"] == "api"


def test_horario_da_interface_e_fallback_identificado():
    doc = normalize_document({**exemplo("DOC-001"), UI_RECEIVED_KEY: "2026-11-17T13:00:00Z"})
    assert doc["received_at_source"] == "interface"
    assert received_label({**doc, "ts": parse_ts(doc["received_at"])}).endswith("*")


def test_evento_com_data_e_considerado_da_api():
    bruto = exemplo("DOC-001")
    bruto["eventos"] = [{"codigo": "X", "descricao": "y", "timestamp_utc": "2026-11-17T10:00:00Z"}]
    doc = normalize_document({**bruto, UI_RECEIVED_KEY: "2026-11-17T13:00:00Z"})
    assert (doc["received_at"], doc["received_at_source"]) == ("2026-11-17T10:00:00Z", "api")


def test_fusos_diferentes_representam_o_mesmo_instante():
    utc = parse_ts("2026-11-17T15:00:00Z")
    brt = parse_ts("2026-11-17T12:00:00-03:00")
    assert utc == brt and utc.tzinfo is None
    assert parse_ts("2026-11-17 12:00:00") == pd.Timestamp("2026-11-17 12:00:00")
    assert parse_ts("data-invalida") is None and parse_ts(None) is None


# --------------------------------------------------------------------------- #
# Filtros temporais
# --------------------------------------------------------------------------- #
AGORA = pd.Timestamp("2026-11-17 15:00:00")


def _docs():
    horas = {"agora": 0, "manha": 6, "ontem_noite": 20, "tres_dias": 72, "dez_dias": 240}
    return [{"id": k, "ts": AGORA - timedelta(hours=h)} for k, h in horas.items()] + [{"id": "sem_data", "ts": None}]


@pytest.mark.parametrize("periodo,esperado", [
    ("Hoje", {"agora", "manha"}),
    ("24 h", {"agora", "manha", "ontem_noite"}),
    ("7 dias", {"agora", "manha", "ontem_noite", "tres_dias"}),
    ("Tudo", {"agora", "manha", "ontem_noite", "tres_dias", "dez_dias", "sem_data"}),
])
def test_filtros_temporais(periodo, esperado):
    inicio, _, _ = _windows(periodo, AGORA)
    assert {d["id"] for d in _between(_docs(), inicio, AGORA)} == esperado


def test_janela_anterior_tem_a_mesma_duracao():
    inicio, ant_inicio, ant_fim = _windows("24 h", AGORA)
    assert inicio - ant_inicio == timedelta(hours=24) and ant_fim == inicio


def test_documento_da_sessao_aparece_em_hoje(monkeypatch):
    """Regressão: sem listagem na API, documentos da sessão sumiam no filtro "Hoje"."""
    api_falsa(monkeypatch, {("GET", "/v1/triagens"): Resposta(501, {"detail": {"mensagem": "x"}})})
    api_client._remember(exemplo("DOC-001"))
    docs = MediFlowClient(BASE).list_documents()
    doc = normalize_document(docs[0])
    agora = pd.Timestamp.now().floor("s") + timedelta(seconds=1)
    inicio, _, _ = _windows("Hoje", agora)
    assert doc["received_at_source"] == "interface"
    assert _between([{**doc, "ts": parse_ts(doc["received_at"])}], inicio, agora)


# --------------------------------------------------------------------------- #
# API indisponível e operações não implementadas
# --------------------------------------------------------------------------- #
def test_api_inacessivel_vira_apierror_amigavel(monkeypatch):
    api_falsa(monkeypatch, {("GET", "/v1/triagens"): requests.exceptions.ConnectionError("recusado")})
    with pytest.raises(APIError, match="Não foi possível conectar"):
        MediFlowClient(BASE).list_documents()


def test_api_com_listagem_libera_revisao(monkeypatch):
    api_falsa(monkeypatch, {("GET", "/v1/triagens"): Resposta(200, [exemplo("DOC-002")])})
    cliente = MediFlowClient(BASE)
    assert cliente.review_supported() is None
    assert [d["documento_id"] for d in cliente.list_documents()] == ["DOC-002"]
    assert cliente.uses_session_data() is False
    assert cliente.review_supported() is True


def test_api_sem_listagem_usa_sessao_e_bloqueia_revisao(monkeypatch):
    api_falsa(monkeypatch, {("GET", "/v1/triagens"): Resposta(404, {"detail": "Not Found"})})
    cliente = MediFlowClient(BASE)
    assert cliente.list_documents() == []
    assert cliente.uses_session_data() is True
    assert cliente.review_supported() is False


def test_revisao_nao_implementada_e_sinalizada(monkeypatch):
    api_falsa(monkeypatch, {("POST", "/v1/triagens/DOC-005/revisao"): Resposta(405, {"detail": "x"})})
    cliente = MediFlowClient(BASE)
    with pytest.raises(APIError, match="não registra revisões"):
        cliente.submit_review("DOC-005", "aprovar", "Auditora")
    assert cliente.review_supported() is False


def test_texto_nao_implementado_tem_mensagem_clara(monkeypatch):
    api_falsa(monkeypatch, {("POST", "/v1/triagens/texto"): Resposta(501, {"detail": {"mensagem": "x"}})})
    with pytest.raises(APIError, match="processa texto colado"):
        MediFlowClient(BASE).submit_text("Texto sintético qualquer")


def test_capacidades_sao_por_url(monkeypatch):
    api_falsa(monkeypatch, {("GET", "/v1/triagens"): Resposta(501, {"detail": "x"})})
    MediFlowClient(BASE).list_documents()
    assert MediFlowClient("http://outra-api.local").review_supported() is None


# --------------------------------------------------------------------------- #
# Fila de auditoria com resultados da sessão
# --------------------------------------------------------------------------- #
def test_fila_de_auditoria_com_resultados_da_sessao(monkeypatch):
    api_falsa(monkeypatch, {("GET", "/v1/triagens"): Resposta(501, {"detail": "x"})})
    for doc_id in ("DOC-001", "DOC-002", "DOC-005"):
        api_client._remember(exemplo(doc_id))
    fila = MediFlowClient(BASE).review_queue()
    assert sorted(d["documento_id"] for d in fila) == ["DOC-002", "DOC-005"]
    assert all(d[UI_RECEIVED_KEY].endswith("Z") for d in fila)


def test_remember_nao_sobrescreve_horario_ja_registrado():
    bruto = {**exemplo("DOC-001"), UI_RECEIVED_KEY: "2026-01-01T00:00:00Z"}
    assert api_client._remember(bruto)[UI_RECEIVED_KEY] == "2026-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Isolamento entre diferentes URLs de API
# ---------------------------------------------------------------------------
def test_resultados_separados_por_api(monkeypatch):
    api_falsa(
        monkeypatch,
        {
            ("GET", "/v1/triagens"): Resposta(
                501, {"detail": {"mensagem": "Nao implementado"}}
            )
        },
    )

    outra = "http://api-b.local"

    st.session_state["api_url"] = BASE
    api_client._remember(exemplo("DOC-001"))

    st.session_state["api_url"] = outra
    api_client._remember(exemplo("DOC-005"))

    ids_a = [
        d["documento_id"]
        for d in MediFlowClient(BASE).list_documents()
    ]
    ids_b = [
        d["documento_id"]
        for d in MediFlowClient(outra).list_documents()
    ]

    assert ids_a == ["DOC-001"]
    assert ids_b == ["DOC-005"]


def test_get_document_nao_usa_resultado_de_outra_api(monkeypatch):
    api_falsa(
        monkeypatch,
        {
            ("GET", "/v1/triagens/DOC-001"): Resposta(
                404, {"detail": "Not Found"}
            )
        },
    )

    st.session_state["api_url"] = BASE
    api_client._remember(exemplo("DOC-001"))

    outra = MediFlowClient("http://api-b.local")

    with pytest.raises(APIError):
        outra.get_document("DOC-001")

    assert (
        MediFlowClient(BASE).get_document("DOC-001")["documento_id"]
        == "DOC-001"
    )


def test_mesmo_documento_id_em_apis_diferentes(monkeypatch):
    api_falsa(
        monkeypatch,
        {
            ("GET", "/v1/triagens"): Resposta(
                501, {"detail": {"mensagem": "Nao implementado"}}
            )
        },
    )

    a = exemplo("DOC-001")
    a["entrada"]["canal_origem"] = "origem-a"

    b = exemplo("DOC-001")
    b["entrada"]["canal_origem"] = "origem-b"

    st.session_state["api_url"] = BASE
    api_client._remember(a)

    st.session_state["api_url"] = "http://api-b.local"
    api_client._remember(b)

    da = MediFlowClient(BASE).list_documents()[0]
    db = MediFlowClient("http://api-b.local").list_documents()[0]

    assert da["entrada"]["canal_origem"] == "origem-a"
    assert db["entrada"]["canal_origem"] == "origem-b"


def test_cliente_grava_na_url_da_instancia(monkeypatch):
    api_falsa(
        monkeypatch,
        {
            ("POST", "/v1/triagens/texto"): Resposta(
                200, exemplo("DOC-005")
            ),
            ("GET", "/v1/triagens"): Resposta(
                501, {"detail": {"mensagem": "Nao implementado"}}
            ),
        },
    )

    st.session_state["api_url"] = BASE

    outra = "http://api-b.local"
    MediFlowClient(outra).submit_text("Texto sintetico de teste")

    assert MediFlowClient(BASE).list_documents() == []

    docs = MediFlowClient(outra).list_documents()
    assert [d["documento_id"] for d in docs] == ["DOC-005"]


def test_ultimo_resultado_respeita_origem_da_api():
    st.session_state["api_url"] = BASE
    api_client.set_last_result(exemplo("DOC-001"))

    assert (
        api_client.get_last_result()["documento_id"]
        == "DOC-001"
    )

    st.session_state["api_url"] = "http://api-b.local"
    assert api_client.get_last_result() is None

    api_client.set_last_result(exemplo("DOC-005"))
    assert (
        api_client.get_last_result()["documento_id"]
        == "DOC-005"
    )

    st.session_state["api_url"] = BASE
    assert api_client.get_last_result() is None

def test_lixeira_texto_oculta_resumo_sem_apagar_resultado():
    from mediflow.ui.views import upload as upload_view

    conteudo = "Documento sintetico DOC-002"
    st.session_state["doc_text"] = conteudo
    st.session_state["_doc_text_read"] = (conteudo, {"words": 3})
    st.session_state["just_processed"] = upload_view._text_source(conteudo)

    api_client.set_last_result(exemplo("DOC-002"))

    upload_view._clear_text()

    assert st.session_state["doc_text"] == ""
    assert st.session_state["just_processed"] is None
    assert "_doc_text_read" not in st.session_state
    assert api_client.get_last_result()["documento_id"] == "DOC-002"


def test_resumo_textual_depende_do_conteudo():
    from mediflow.ui.views import upload as upload_view

    origem_a = upload_view._text_source("Documento sintetico A")
    origem_b = upload_view._text_source("Documento sintetico B")

    assert origem_a != origem_b
    assert origem_a == upload_view._text_source("Documento sintetico A  ")


def test_trocar_amostra_oculta_resumo_anterior():
    from mediflow.ui.views import upload as upload_view

    st.session_state["doc_text"] = "Documento anterior"
    st.session_state["_doc_text_read"] = ("Documento anterior", {})
    st.session_state["just_processed"] = upload_view._text_source(
        "Documento anterior"
    )

    arquivo = upload_view.SAMPLE_TEXTS["Ambiguidade (DOC-005)"]
    upload_view._load_sample(arquivo)

    assert st.session_state["doc_text"] == (
        upload_view.SAMPLE_TEXTS_DIR / arquivo
    ).read_text(encoding="utf-8").strip()
    assert st.session_state["just_processed"] is None
    assert "_doc_text_read" not in st.session_state

def test_resumo_arquivo_aparece_depois_do_preview(monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace
    from mediflow.ui.views import upload as tela

    eventos = []
    arquivo = SimpleNamespace(
        name="DOC-002_laudo_imagem_alerta.pdf",
        size=100,
        type="application/pdf",
    )

    monkeypatch.setattr(st, "subheader", lambda *a, **k: None)
    monkeypatch.setattr(st, "file_uploader", lambda *a, **k: arquivo)
    monkeypatch.setattr(st, "html", lambda *a, **k: None)
    monkeypatch.setattr(
        st, "columns",
        lambda *a, **k: (nullcontext(), nullcontext()),
    )
    monkeypatch.setattr(st, "button", lambda *a, **k: False)

    monkeypatch.setattr(tela, "_validate", lambda uploaded: None)
    monkeypatch.setattr(
        tela, "_upload_success",
        lambda *a, **k: eventos.append("arquivo"),
    )
    monkeypatch.setattr(
        tela, "_preview",
        lambda uploaded: eventos.append("preview"),
    )
    monkeypatch.setattr(
        tela, "_show_last_result",
        lambda source: eventos.append("resumo"),
    )

    tela._file_mode(None)

    assert eventos == ["arquivo", "preview", "resumo"]

# Regressao da Visao geral: rejeitar encerra fluxo, mas nao aprova o documento.
def test_finalizados_incluem_rejeitados_e_filtro_seleciona_todos(monkeypatch):
    from contextlib import nullcontext

    from mediflow.ui.components import status_label
    from mediflow.ui.config import DONE_STATUSES
    from mediflow.ui.models import compute_stats
    from mediflow.ui.views import dashboard

    originais = [exemplo("DOC-001"), exemplo("DOC-002"), exemplo("DOC-005")]
    originais[1]["revisao_humana"] = {"acao": "rejeitar", "revisor": "Auditor Sintetico"}
    originais[2]["revisao_humana"] = {"acao": "aprovar", "revisor": "Auditor Sintetico"}
    docs = [normalize_document(d) for d in originais]

    assert [d["status"] for d in docs] == ["processed", "rejected", "approved"]
    assert set(DONE_STATUSES) == {"processed", "approved", "corrected", "rejected"}
    assert compute_stats(originais)["processed"] == 3

    cards = {}

    def registrar_card(chave, rotulo, icone, valor, **kwargs):
        cards[chave] = {"rotulo": rotulo, "valor": valor, "on_click": kwargs.get("on_click")}

    monkeypatch.setattr(dashboard, "_kpi_card", registrar_card)
    monkeypatch.setattr(dashboard.st, "container", lambda *a, **k: nullcontext())
    dashboard._kpis(docs, docs, None, "24 h")

    card = cards["card_kpi_done"]
    assert card["rotulo"] == "Finalizados"
    assert card["valor"] == 3
    card["on_click"]()
    assert set(st.session_state[dashboard.K_STATUS]) == {status_label(s) for s in DONE_STATUSES}
    assert "Rejeitado" in st.session_state[dashboard.K_STATUS]


def test_linha_do_tempo_nao_conta_rejeitado_duas_vezes():
    from mediflow.ui.views import dashboard

    agora = pd.Timestamp("2026-11-20 15:30:00")
    docs = [
        {"ts": agora - timedelta(hours=1), "status": "processed"},
        {"ts": agora - timedelta(hours=2), "status": "approved"},
        {"ts": agora - timedelta(hours=3), "status": "rejected"},
    ]
    frame = dashboard._timeline_frame(docs, agora - timedelta(hours=24), agora, "24 h")
    assert frame is not None
    totais = frame.groupby("grupo")["total"].sum().to_dict()
    assert totais["Concluídos"] == 2
    assert totais["Rejeitados"] == 1
    assert sum(totais.values()) == 3


def test_upload_amostra_nao_autorizada_mensagem_clara(monkeypatch):
    chamadas = api_falsa(monkeypatch, {
        ("POST", "/v1/triagens/arquivos"): Resposta(422, {
            "detail": {
                "codigo": "AMOSTRA_NAO_AUTORIZADA",
                "mensagem": "Amostra fora do catalogo da demonstracao.",
            }
        }),
    })

    with pytest.raises(APIError, match="Arquivo fora das amostras autorizadas"):
        MediFlowClient(BASE).upload_document(
            "arquivo_externo.pdf", b"%PDF-1.4", "application/pdf"
        )
    assert len(chamadas) == 1
    assert chamadas[0][0] == "POST"
    assert chamadas[0][1].endswith("/v1/triagens/arquivos")


# --------------------------------------------------------------------------- #
# Ajuste 6 - revisao humana: comparativo sem sobrescrever extracao original
# --------------------------------------------------------------------------- #
def test_revisao_corrigida_mostra_original_e_correcao():
    import copy

    raw = exemplo("DOC-005")
    antes = copy.deepcopy(raw)
    raw["revisao_humana"] = {
        "acao": "corrigir", "revisor": "Auditor Sintetico",
        "revisado_em": "2026-11-20T20:00:00Z",
        "comentario": "Conferencia com fonte sintetica complementar",
        "chave_resultado": "resultados/DOC-005/sintetico",
        "correcoes": {
            "classificacao": {"nivel_prioridade_documental": "rotina"},
            "decisao_roteamento": {"destino_principal": "prontuario_documental"},
            "dados_extraidos": {
                "paciente": {"nome": "Paciente Sintetico Revisado", "nome_status": "legivel"},
                "medicamentos": [{"nome": "Medicamento Alfa (ficticio)",
                                  "dosagem_texto": "DOSE_SINTETICA_CONFIRMADA", "dosagem_status": "legivel"}],
            },
        },
    }
    doc = normalize_document(raw)
    assert doc["status"] == "corrected"
    assert doc["review"]["reviewer"] == "Auditor Sintetico"
    assert doc["review"]["comment"] == "Conferencia com fonte sintetica complementar"
    assert doc["review"]["result_key"] == "resultados/DOC-005/sintetico"
    changes = {c["path"]: c for c in doc["review"]["changes"]}
    assert changes["classificacao.nivel_prioridade_documental"]["corrected"] == "Rotina"
    assert changes["decisao_roteamento.destino_principal"]["corrected"] == "Prontuário"
    assert changes["dados_extraidos.paciente.nome"]["corrected"] == "Paciente Sintetico Revisado"
    assert "ileg" in changes["dados_extraidos.medicamentos"]["original"].lower()
    assert "DOSE_SINTETICA_CONFIRMADA" in changes["dados_extraidos.medicamentos"]["corrected"]
    assert doc["extracted"]["medications"][0]["dosage"].lower().startswith("(ileg")
    assert {k: v for k, v in raw.items() if k != "revisao_humana"} == antes


def test_aprovacao_sem_correcao_nao_cria_comparativo():
    raw = exemplo("DOC-001")
    raw["revisao_humana"] = {"acao": "aprovar", "revisor": "Auditor Sintetico",
                             "revisado_em": "2026-11-20T20:00:00Z", "correcoes": {}}
    doc = normalize_document(raw)
    assert doc["review"]["changes"] == []
    assert doc["status"] == "approved"


def test_correcao_desconhecida_tambem_aparece_no_comparativo():
    raw = exemplo("DOC-002")
    raw["revisao_humana"] = {
        "acao": "corrigir", "revisor": "Auditor Sintetico",
        "correcoes": {"dados_extraidos": {"campo_futuro": "valor sintetico"}},
    }
    row = normalize_document(raw)["review"]["changes"]
    assert len(row) == 1
    assert row[0]["path"] == "dados_extraidos.campo_futuro"
    assert row[0]["original"] == "—"
    assert row[0]["corrected"] == "valor sintetico"


def test_resultado_renderiza_comparativo_de_revisao(monkeypatch):
    from contextlib import nullcontext
    from mediflow.ui.views import result as tela

    raw = exemplo("DOC-005")
    raw["revisao_humana"] = {
        "acao": "corrigir", "revisor": "Auditor Sintetico",
        "correcoes": {"dados_extraidos": {"paciente": {"nome": "Nome Sintetico Corrigido"}}},
    }
    exibidos = []
    monkeypatch.setattr(st, "container", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(st, "markdown", lambda *args, **kwargs: None)
    monkeypatch.setattr(st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(st, "dataframe", lambda frame, **kwargs: exibidos.append(frame))

    tela._review(normalize_document(raw))

    assert len(exibidos) == 1
    assert list(exibidos[0].columns) == ["Campo", "Extração original", "Correção humana"]
    assert exibidos[0].iloc[0]["Correção humana"] == "Nome Sintetico Corrigido"


# --------------------------------------------------------------------------- #
# Ajuste 8 - apresentação separada da triagem original e da decisão humana
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "acao,estado,cartao,rotulo",
    [
        ("aprovar", "approved", "card_ok_review", "Aprovado sem alterações"),
        ("corrigir", "corrected", "card_warn_review", "Aprovado com correções"),
        ("rejeitar", "rejected", "card_alert_review", "Rejeitado"),
    ],
)
def test_ajuste8_revisao_humana_com_identidade_visual(
    monkeypatch, acao, estado, cartao, rotulo
):
    from contextlib import nullcontext
    from mediflow.ui.views import result as tela

    raw = exemplo("DOC-005")
    raw["revisao_humana"] = {
        "acao": acao,
        "revisor": "Revisor Sintetico",
        "revisado_em": "2026-11-20T20:00:00Z",
        "comentario": "Verificacao educativa",
        "correcoes": (
            {"dados_extraidos": {"paciente": {"nome": "Nome Sintetico Corrigido"}}}
            if acao == "corrigir" else {}
        ),
    }
    doc = normalize_document(raw)
    cartoes = []
    mensagens = []

    def container(*args, **kwargs):
        cartoes.append(kwargs.get("key"))
        return nullcontext()

    monkeypatch.setattr(st, "container", container)
    monkeypatch.setattr(st, "markdown", lambda value, **kwargs: mensagens.append(str(value)))
    monkeypatch.setattr(st, "caption", lambda value, **kwargs: mensagens.append(str(value)))
    monkeypatch.setattr(st, "dataframe", lambda *args, **kwargs: None)

    tela._review(doc)

    assert doc["status"] == estado
    assert cartao in cartoes
    assert any("Decisão humana: " + rotulo in msg for msg in mensagens)
    assert any("Revisor informado: Revisor Sintetico" in msg for msg in mensagens)
    assert any("não altera a triagem automatizada original" in msg for msg in mensagens)
    assert doc["priority"] == "ambiguidade"
    assert doc["destination_id"] == "auditoria_humana"


def test_ajuste8_kpis_sao_identificados_como_originais(monkeypatch):
    from contextlib import nullcontext
    from mediflow.ui.views import result as tela

    raw = exemplo("DOC-005")
    raw["revisao_humana"] = {
        "acao": "corrigir", "revisor": "Revisor Sintetico",
        "correcoes": {"classificacao": {"nivel_prioridade_documental": "rotina"}},
    }
    doc = normalize_document(raw)
    textos = []
    metricas = []
    monkeypatch.setattr(st, "container", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(st, "markdown", lambda value, **kwargs: textos.append(str(value)))
    monkeypatch.setattr(st, "caption", lambda value, **kwargs: textos.append(str(value)))
    monkeypatch.setattr(st, "metric", lambda label, value, **kwargs: metricas.append((label, value)))

    tela._kpis(doc)

    assert any("Triagem automatizada — resultado original" in text for text in textos)
    assert any("decisão humana posterior" in text for text in textos)
    assert ("Prioridade documental", "Indeterminada") in metricas
    assert ("Destino", "Auditoria humana") in metricas
    assert doc["review"]["changes"][0]["corrected"] == "Rotina"



# Ajuste 8B - edicoes declaradas ao rejeitar, sem aprovar nem substituir a IA.
def test_ajuste8b_seletor_de_correcoes_preserva_rejeicao():
    from mediflow.ui.views.audit import _corrections_for_review

    alteracoes = {"dados_extraidos": {"paciente": {"nome": "Nome Ficticio"}}}
    assert _corrections_for_review("rejeitar", alteracoes) == alteracoes
    assert _corrections_for_review("corrigir", alteracoes) == alteracoes
    assert _corrections_for_review("aprovar", alteracoes) is None
    assert _corrections_for_review("rejeitar", {}) is None


def test_ajuste8b_rejeicao_com_edicoes_exibe_comparativo(monkeypatch):
    from contextlib import nullcontext
    from mediflow.ui.views import result as tela

    raw = exemplo("DOC-005")
    nome_original = raw["dados_extraidos"]["paciente"].get("nome")
    raw["revisao_humana"] = {
        "acao": "rejeitar", "revisor": "Revisor Sintetico",
        "comentario": "Rejeicao com registros de alteracao",
        "correcoes": {"dados_extraidos": {"paciente": {"nome": "Outro Nome Ficticio"}}},
    }
    doc = normalize_document(raw)
    titulos = []
    tabelas = []
    monkeypatch.setattr(st, "container", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(st, "markdown", lambda txt, **kwargs: titulos.append(str(txt)))
    monkeypatch.setattr(st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(st, "dataframe", lambda frame, **kwargs: tabelas.append(frame))

    tela._review(doc)
    assert doc["status"] == "rejected"
    assert doc["extracted"]["patient_name"] == nome_original
    assert any("Alterações informadas durante a rejeição" in t for t in titulos)
    assert len(tabelas) == 1
    assert tabelas[0].iloc[0]["Extração original"] == nome_original
    assert tabelas[0].iloc[0]["Correção humana"] == "Outro Nome Ficticio"


def test_ajuste8b_rejeicao_sem_edicoes_nao_exibe_comparativo(monkeypatch):
    from contextlib import nullcontext
    from mediflow.ui.views import result as tela

    raw = exemplo("DOC-005")
    raw["revisao_humana"] = {
        "acao": "rejeitar", "revisor": "Revisor Sintetico", "comentario": "Rejeitado",
        "correcoes": {},
    }
    tabelas = []
    monkeypatch.setattr(st, "container", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(st, "markdown", lambda *args, **kwargs: None)
    monkeypatch.setattr(st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(st, "dataframe", lambda frame, **kwargs: tabelas.append(frame))

    tela._review(normalize_document(raw))
    assert tabelas == []
