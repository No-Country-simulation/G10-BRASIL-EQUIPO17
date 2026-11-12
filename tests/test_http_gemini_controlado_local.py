"""Integra Gemini ao fluxo por dependencia injetada; NUNCA acessa Gemini/OCI reais."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mediflow.api.app import app as app_principal
from mediflow.api.app_demo_local import ExtratorFixtureSintetica, cliente_fakeoci
from mediflow.api.app_gemini_local import (
    app,
    fornecer_extrator_gemini,
)
from mediflow.extraction.port import DocumentoParaExtracao
from mediflow_contracts.models import ResultadoTriagem

RAIZ = Path(__file__).resolve().parents[1]
ARQUIVOS = {
    "DOC-001": ("amostras/pdf/DOC-001_laudo_laboratorial_rotina.pdf", "application/pdf", "R005", "prontuario_documental", "processado"),
    "DOC-002": ("amostras/pdf/DOC-002_laudo_imagem_alerta.pdf", "application/pdf", "R001", "fila_prioritaria_avaliacao_humana", "aguardando_auditoria"),
    "DOC-005": ("amostras/imagens/DOC-005_receita_ilegivel.png", "image/png", "R002", "auditoria_humana", "aguardando_auditoria"),
}


class ExtratorControlado:
    def __init__(self):
        self.chamadas: list[DocumentoParaExtracao] = []

    def extrair(self, documento: DocumentoParaExtracao):
        self.chamadas.append(documento)
        return ExtratorFixtureSintetica().extrair(documento)


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.setenv("MEDIFLOW_ENV", "development")
    monkeypatch.setenv("MEDIFLOW_ENABLE_LOCAL_UPLOADS", "true")
    monkeypatch.setenv("MEDIFLOW_ENABLE_LOCAL_TRIAGE", "true")
    monkeypatch.setenv("MEDIFLOW_ENABLE_LOCAL_GEMINI", "true")
    monkeypatch.delenv("MEDIFLOW_GEMINI_REAL_ACK", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    cliente_fakeoci.objetos.clear()
    cliente_fakeoci.falhar_prefixo = None
    app.dependency_overrides.pop(fornecer_extrator_gemini, None)
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(fornecer_extrator_gemini, None)
        cliente_fakeoci.objetos.clear()
        cliente_fakeoci.falhar_prefixo = None


def enviar(cliente, doc_id: str, *, conteudo_override: bytes | None = None):
    relativo, mime, *_ = ARQUIVOS[doc_id]
    caminho = RAIZ / relativo
    conteudo = caminho.read_bytes() if conteudo_override is None else conteudo_override
    resposta = cliente.post(
        "/v1/triagens/arquivos",
        data={"documento_id": doc_id, "canal_origem": "homologacao_local"},
        files={"arquivo": (caminho.name, conteudo, mime)},
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def processar(cliente, recibo):
    return cliente.post(
        f"/v1/triagens/arquivos/{recibo['documento_id']}/{recibo['arquivo_id']}/processar"
    )


@pytest.mark.parametrize("doc_id", list(ARQUIVOS))
def test_pipeline_http_controlado_sem_chamar_gemini(cliente, doc_id):
    extrator = ExtratorControlado()
    app.dependency_overrides[fornecer_extrator_gemini] = lambda: extrator
    recibo = enviar(cliente, doc_id)
    resposta = processar(cliente, recibo)
    assert resposta.status_code == 200, resposta.text
    assert "fakeoci" in resposta.headers["X-MediFlow-Mode"].lower()
    resultado = ResultadoTriagem.model_validate(resposta.json())
    _, _, regra, destino, status = ARQUIVOS[doc_id]
    assert resultado.documento_id == doc_id
    assert resultado.decisao_roteamento.regra_principal == regra
    assert resultado.decisao_roteamento.destino_principal == destino
    assert resultado.status == status
    assert resultado.rag.status == "consultado"
    assert resultado.armazenamento_oci.bucket == "FAKEOCI-SOMENTE-MEMORIA"
    assert len(extrator.chamadas) == 1
    assert extrator.chamadas[0].sha256 == recibo["entrada"]["sha256"]
    assert ResultadoTriagem.model_validate_json(
        cliente_fakeoci.objetos[resultado.armazenamento_oci.chave_resultado]
    ) == resultado
    if doc_id == "DOC-005":
        assert resultado.dados_extraidos.medicamentos[0].dosagem_texto is None


def test_informacoes_de_modo_nao_comprovam_chamada_real(cliente):
    r = cliente.get("/gemini/estado")
    assert r.status_code == 200
    assert r.json()["gemini_real_habilitado"] is False
    assert r.json()["oci_real"] is False
    assert r.headers["Cache-Control"] == "no-store"


def test_sem_flag_de_modo_bloqueia_antes_do_upload(cliente, monkeypatch):
    monkeypatch.delenv("MEDIFLOW_ENABLE_LOCAL_GEMINI")
    assert cliente.get("/gemini/estado").status_code == 403
    r = cliente.post("/v1/triagens/arquivos/DOC-001/" + "a" * 32 + "/processar")
    assert r.status_code == 403
    assert r.json()["detail"]["codigo"] == "GEMINI_LOCAL_DESABILITADO"
    assert not cliente_fakeoci.objetos


def test_ambiente_nao_development_bloqueado(cliente, monkeypatch):
    monkeypatch.setenv("MEDIFLOW_ENV", "production")
    assert cliente.get("/gemini/estado").status_code == 403


def test_sem_consentimento_bloqueia_gemini_real(cliente):
    recibo = enviar(cliente, "DOC-001")
    r = processar(cliente, recibo)
    assert r.status_code == 503
    assert r.json()["detail"]["codigo"] == "GEMINI_REAL_NAO_AUTORIZADO"
    assert not any(chave.startswith("resultados/") for chave in cliente_fakeoci.objetos)


def test_sem_chave_bloqueia_mesmo_com_consentimento(cliente, monkeypatch):
    monkeypatch.setenv("MEDIFLOW_GEMINI_REAL_ACK", "AUTORIZO_CHAMADAS_GEMINI")
    recibo = enviar(cliente, "DOC-001")
    r = processar(cliente, recibo)
    assert r.status_code == 503
    assert r.json()["detail"]["codigo"] == "GEMINI_REAL_NAO_CONFIGURADO"


def test_arquivo_incorreto_nao_chega_ao_extrator(cliente):
    extrator = ExtratorControlado()
    app.dependency_overrides[fornecer_extrator_gemini] = lambda: extrator
    dados_outro = (RAIZ / ARQUIVOS["DOC-002"][0]).read_bytes()
    recibo = enviar(cliente, "DOC-001", conteudo_override=dados_outro)
    r = processar(cliente, recibo)
    assert r.status_code == 502
    assert r.json()["detail"]["codigo"] == "EXTRACAO_INDISPONIVEL"
    assert extrator.chamadas == []
    assert not any(chave.startswith("resultados/") for chave in cliente_fakeoci.objetos)


def test_original_corrompido_bloqueia_antes_do_extrator(cliente):
    extrator = ExtratorControlado()
    app.dependency_overrides[fornecer_extrator_gemini] = lambda: extrator
    recibo = enviar(cliente, "DOC-001")
    cliente_fakeoci.objetos[recibo["armazenamento_original"]["chave_original"]] = b"CORROMPIDO"
    r = processar(cliente, recibo)
    assert r.status_code == 502
    assert r.json()["detail"]["codigo"] == "INTEGRIDADE_ORIGINAL_INVALIDA"
    assert extrator.chamadas == []


def test_falha_de_extracao_nao_vaza_segredos(cliente):
    class ExtratorFalho:
        def extrair(self, documento):
            raise RuntimeError("GEMINI_API_KEY=SEGREDO_FICTICIO_NAO_PUBLICAR")

    app.dependency_overrides[fornecer_extrator_gemini] = lambda: ExtratorFalho()
    recibo = enviar(cliente, "DOC-001")
    r = processar(cliente, recibo)
    assert r.status_code == 502
    assert r.json()["detail"]["codigo"] == "EXTRACAO_INDISPONIVEL"
    assert "SEGREDO_FICTICIO_NAO_PUBLICAR" not in r.text


def test_falha_de_persistencia_nao_declara_sucesso(cliente):
    app.dependency_overrides[fornecer_extrator_gemini] = lambda: ExtratorControlado()
    recibo = enviar(cliente, "DOC-001")
    cliente_fakeoci.falhar_prefixo = "resultados/"
    r = processar(cliente, recibo)
    assert r.status_code == 502
    assert r.json()["detail"]["codigo"] == "PERSISTENCIA_INDISPONIVEL"
    assert not any(chave.startswith("resultados/") for chave in cliente_fakeoci.objetos)


def test_api_principal_permanece_sem_rota_processar():
    assert not any(
        getattr(r, "path", "").endswith("/processar")
        for r in app_principal.routes
    )
