"""Cliente da UI na triagem por texto (aba "Texto livre"), sem rede real."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

st = pytest.importorskip("streamlit")  # extra `ui`; ausente na CI sem ele
requests = pytest.importorskip("requests")

from mediflow.ui.api_client import APIError, MediFlowClient  # noqa: E402
from mediflow.ui.config import SAMPLE_TEXTS, SAMPLE_TEXTS_DIR  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
BASE = "http://api-teste.local"


@pytest.fixture(autouse=True)
def sessao_limpa():
    st.session_state.clear()
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


def responder_texto(monkeypatch, resposta: Resposta) -> None:
    def request(method, url, **kwargs):
        assert method == "POST" and url.endswith("/v1/triagens/texto")
        assert set(kwargs["json"]) >= {"documento_id", "canal_origem", "documento_texto"}
        return resposta

    monkeypatch.setattr(requests, "request", request)


def test_texto_nao_implementado_tem_mensagem_clara(monkeypatch):
    responder_texto(monkeypatch, Resposta(501, {"detail": {"mensagem": "x"}}))
    with pytest.raises(APIError, match="não processa texto colado"):
        MediFlowClient(BASE).submit_text("Texto sintético qualquer")


def test_texto_fora_das_amostras_explica_a_restricao(monkeypatch):
    erro = {"detail": {"codigo": "TEXTO_NAO_AUTORIZADO", "mensagem": "x"}}
    responder_texto(monkeypatch, Resposta(422, erro))
    with pytest.raises(APIError, match="amostras sintéticas oficiais") as exc:
        MediFlowClient(BASE).submit_text("Texto sintético qualquer")
    assert exc.value.status_code == 422


def test_texto_processado_e_guardado_na_sessao(monkeypatch):
    corpo = json.loads((RAIZ / "exemplos" / "DOC-001_resultado.json").read_text(encoding="utf-8"))
    responder_texto(monkeypatch, Resposta(200, corpo))
    resultado = MediFlowClient(BASE).submit_text("Texto sintético qualquer")
    assert resultado["documento_id"] == "DOC-001"


def test_amostras_de_texto_da_interface_existem():
    for nome in SAMPLE_TEXTS.values():
        assert (SAMPLE_TEXTS_DIR / nome).is_file(), nome
