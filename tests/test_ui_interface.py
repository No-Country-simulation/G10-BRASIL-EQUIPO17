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
