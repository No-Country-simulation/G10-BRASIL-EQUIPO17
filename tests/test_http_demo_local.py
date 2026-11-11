"""HTTP demonstrativo: processamento REAL local de regras/RAG/LangGraph, mas fixture e FakeOCI.

A aplicacao principal continua sem o endpoint de processamento.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mediflow.api.app import app as app_principal
from mediflow.api.app_demo_local import app, cliente_fakeoci
from mediflow_contracts.models import ResultadoTriagem

RAIZ = Path(__file__).resolve().parents[1]
ARQUIVOS = {
    "DOC-001": ("amostras/pdf/DOC-001_laudo_laboratorial_rotina.pdf", "application/pdf", "R005", "prontuario_documental"),
    "DOC-002": ("amostras/pdf/DOC-002_laudo_imagem_alerta.pdf", "application/pdf", "R001", "fila_prioritaria_avaliacao_humana"),
    "DOC-005": ("amostras/imagens/DOC-005_receita_ilegivel.png", "image/png", "R002", "auditoria_humana"),
}


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.setenv("MEDIFLOW_ENV", "development")
    monkeypatch.setenv("MEDIFLOW_ENABLE_LOCAL_UPLOADS", "true")
    monkeypatch.setenv("MEDIFLOW_ENABLE_LOCAL_TRIAGE", "true")
    monkeypatch.setenv("MEDIFLOW_ENABLE_LOCAL_DEMO", "true")
    cliente_fakeoci.objetos.clear()
    cliente_fakeoci.falhar_prefixo = None
    with TestClient(app) as c:
        yield c
    cliente_fakeoci.objetos.clear()
    cliente_fakeoci.falhar_prefixo = None


def enviar(c, doc_id, *, arquivo_override=None):
    relativo, mime, _, _ = ARQUIVOS[doc_id]
    arquivo = RAIZ / relativo
    bytes_documento = arquivo.read_bytes() if arquivo_override is None else arquivo_override
    r = c.post(
        "/v1/triagens/arquivos",
        data={"documento_id": doc_id, "canal_origem": "demo_local"},
        files={"arquivo": (arquivo.name, bytes_documento, mime)},
    )
    assert r.status_code == 201, r.text
    return r.json()


def processar(c, recibo):
    return c.post(f"/v1/triagens/arquivos/{recibo['documento_id']}/{recibo['arquivo_id']}/processar")


@pytest.mark.parametrize("doc_id", list(ARQUIVOS))
def test_processamento_http_com_rag_langgraph_e_fakeoci(cliente, doc_id):
    recibo = enviar(cliente, doc_id)
    r = processar(cliente, recibo)
    assert r.status_code == 200, r.text
    assert "fakeoci" in r.headers["X-MediFlow-Mode"].lower()
    dados = r.json()
    saida = ResultadoTriagem.model_validate(dados)
    _, _, regra, destino = ARQUIVOS[doc_id]
    assert dados["documento_id"] == doc_id
    assert dados["decisao_roteamento"]["regra_principal"] == regra
    assert dados["decisao_roteamento"]["destino_principal"] == destino
    assert dados["rag"]["status"] == "consultado"
    assert dados["armazenamento_oci"]["status"] == "confirmado"
    assert dados["entrada"]["sha256"] == recibo["entrada"]["sha256"]
    chave = dados["armazenamento_oci"]["chave_resultado"]
    assert ResultadoTriagem.model_validate_json(cliente_fakeoci.objetos[chave]) == saida
    if doc_id == "DOC-005":
        medicamento = dados["dados_extraidos"]["medicamentos"][0]
        assert medicamento["dosagem_texto"] is None
        assert medicamento["dosagem_status"] == "ilegivel"


def test_modo_demo_fica_identificado(cliente):
    r = cliente.get("/demo/estado")
    assert r.status_code == 200
    assert r.json()["gemini_real"] is False
    assert r.json()["oci_real"] is False
    assert r.headers["Cache-Control"] == "no-store"


def test_app_principal_continua_sem_processar():
    assert not any(
        getattr(r, "path", "").endswith("/processar")
        for r in app_principal.routes
    )


def test_sem_flag_demonstracao_retorna_403_antes_do_upload(cliente, monkeypatch):
    monkeypatch.delenv("MEDIFLOW_ENABLE_LOCAL_DEMO")
    assert cliente.get("/demo/estado").status_code == 403
    r = cliente.post("/v1/triagens/arquivos/DOC-001/" + "a" * 32 + "/processar")
    assert r.status_code == 403
    assert r.json()["detail"]["codigo"] == "DEMO_LOCAL_DESABILITADA"
    assert cliente_fakeoci.objetos == {}


def test_ambiente_producao_rejeitado(cliente, monkeypatch):
    monkeypatch.setenv("MEDIFLOW_ENV", "production")
    assert cliente.get("/demo/estado").status_code == 403


def test_sem_manifesto_retorna_404(cliente):
    r = cliente.post("/v1/triagens/arquivos/DOC-001/" + "a" * 32 + "/processar")
    assert r.status_code == 404
    assert r.json()["detail"]["codigo"] == "REGISTRO_NAO_ENCONTRADO"


def test_original_corrompido_bloqueia_processamento(cliente):
    recibo = enviar(cliente, "DOC-001")
    chave_original = recibo["armazenamento_original"]["chave_original"]
    cliente_fakeoci.objetos[chave_original] = b"CORROMPIDO"
    r = processar(cliente, recibo)
    assert r.status_code == 502
    assert r.json()["detail"]["codigo"] == "INTEGRIDADE_ORIGINAL_INVALIDA"
    assert not any(k.startswith("resultados/") for k in cliente_fakeoci.objetos)


def test_amostra_diferente_da_oficial_rejeitada(cliente):
    doc_2 = (RAIZ / ARQUIVOS["DOC-002"][0]).read_bytes()
    recibo = enviar(cliente, "DOC-001", arquivo_override=doc_2)
    r = processar(cliente, recibo)
    assert r.status_code == 502
    assert r.json()["detail"]["codigo"] == "EXTRACAO_INDISPONIVEL"
    assert not any(k.startswith("resultados/") for k in cliente_fakeoci.objetos)


def test_falha_na_persistencia_nao_declara_sucesso(cliente):
    recibo = enviar(cliente, "DOC-001")
    cliente_fakeoci.falhar_prefixo = "resultados/"
    r = processar(cliente, recibo)
    assert r.status_code == 502
    assert r.json()["detail"]["codigo"] == "PERSISTENCIA_INDISPONIVEL"
    assert not any(k.startswith("resultados/") for k in cliente_fakeoci.objetos)
