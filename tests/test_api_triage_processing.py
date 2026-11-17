"""Testes da nova rota I1 sem Gemini, LangGraph ou credenciais OCI."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mediflow.api.triage_processing import obter_servico_triagem, router
from mediflow.api.app import app as app_develop
from mediflow.api.triage_service import FalhaOrquestracao
from mediflow.api.uploads import armazenamento, router as upload_router
from mediflow.extraction.port import DocumentoParaExtracao
from mediflow_contracts.models import ResultadoTriagem

RAIZ = Path(__file__).resolve().parents[1]
AMOSTRAS = {
    "DOC-001": ("amostras/pdf/DOC-001_laudo_laboratorial_rotina.pdf", "application/pdf"),
    "DOC-002": ("amostras/pdf/DOC-002_laudo_imagem_alerta.pdf", "application/pdf"),
    "DOC-005": ("amostras/imagens/DOC-005_receita_ilegivel.png", "image/png"),
}


class FakeOCI:
    bucket = "bucket-sintetico"

    def __init__(self):
        self.objetos: dict[str, bytes] = {}
        self.reads: list[str] = []
        self.fail_prefix: str | None = None

    def upload_bytes(self, key: str, content: bytes, content_type: str = "application/octet-stream") -> str:
        self.objetos[key] = content
        return hashlib.sha256(content).hexdigest()

    def download_bytes(self, key: str) -> bytes:
        self.reads.append(key)
        if self.fail_prefix and key.startswith(self.fail_prefix):
            raise RuntimeError("OCI_API_KEY=SEGREDO_QUE_NAO_DEVE_APARECER")
        if key not in self.objetos:
            erro = LookupError("nao encontrado")
            erro.status = 404
            raise erro
        return self.objetos[key]


class ServicoSimulado:
    """Retorna gabaritos de contrato; NAO faz OCR, decisao LangGraph nem OCI real."""

    def __init__(self):
        self.chamadas: list[tuple[DocumentoParaExtracao, str]] = []
        self.falha: Exception | None = None
        self.retorno_forcado = None

    def executar(self, documento: DocumentoParaExtracao, *, canal_origem: str):
        self.chamadas.append((documento, canal_origem))
        if self.falha is not None:
            raise self.falha
        if self.retorno_forcado is not None:
            return self.retorno_forcado
        raw = json.loads((RAIZ / f"exemplos/{documento.documento_id}_resultado.json").read_text(encoding="utf-8"))
        raw["entrada"]["canal_origem"] = canal_origem
        raw["entrada"]["sha256"] = documento.sha256
        raw["entrada"]["nome_arquivo"] = documento.nome_original
        return ResultadoTriagem.model_validate(raw)


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("MEDIFLOW_ENV", "development")
    monkeypatch.setenv("MEDIFLOW_ENABLE_LOCAL_UPLOADS", "true")
    monkeypatch.setenv("MEDIFLOW_ENABLE_LOCAL_TRIAGE", "true")
    storage, servico = FakeOCI(), ServicoSimulado()
    app = FastAPI()
    app.include_router(upload_router)
    app.include_router(router)
    app.dependency_overrides[armazenamento] = lambda: storage
    app.dependency_overrides[obter_servico_triagem] = lambda: servico
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, storage=storage, servico=servico, app=app)


def enviar(api, documento_id="DOC-001"):
    caminho, mime = AMOSTRAS[documento_id]
    p = RAIZ / caminho
    r = api.client.post(
        "/v1/triagens/arquivos",
        data={"documento_id": documento_id, "canal_origem": "teste_sintetico"},
        files={"arquivo": (p.name, p.read_bytes(), mime)},
    )
    assert r.status_code == 201, r.text
    return r.json()


def processar(api, recibo):
    return api.client.post(
        f"/v1/triagens/arquivos/{recibo['documento_id']}/{recibo['arquivo_id']}/processar"
    )


def alterar_manifesto(api, recibo, operacao):
    chave = recibo["registro_metadados"]["chave_metadados"]
    dados = json.loads(api.storage.objetos[chave])
    operacao(dados)
    api.storage.objetos[chave] = json.dumps(dados).encode("utf-8")


@pytest.mark.parametrize("documento_id,regra,estado", [
    ("DOC-001", "R005", "processado"),
    ("DOC-002", "R001", "aguardando_auditoria"),
    ("DOC-005", "R002", "aguardando_auditoria"),
])
def test_tres_cenarios_sinteticos_por_fakes(api, documento_id, regra, estado):
    recibo = enviar(api, documento_id)
    api.storage.reads.clear()
    r = processar(api, recibo)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["documento_id"] == documento_id
    assert body["status"] == estado
    assert body["decisao_roteamento"]["regra_principal"] == regra
    assert body["armazenamento_oci"]["status"] == "pendente"
    assert len(api.servico.chamadas) == 1
    original, canal = api.servico.chamadas[0]
    assert original.documento_id == documento_id
    assert original.arquivo_id == recibo["arquivo_id"]
    assert original.nome_original == recibo["entrada"]["nome_arquivo"]
    assert original.sha256 == recibo["entrada"]["sha256"]
    assert original.mime_type == AMOSTRAS[documento_id][1]
    assert hashlib.sha256(original.conteudo).hexdigest() == original.sha256
    assert canal == "teste_sintetico"
    assert api.storage.reads == [
        recibo["registro_metadados"]["chave_metadados"],
        recibo["armazenamento_original"]["chave_original"],
    ]


def test_documento_nao_pode_ser_processado_sem_flag_especifica(api, monkeypatch):
    recibo = enviar(api)
    api.storage.reads.clear()
    monkeypatch.setenv("MEDIFLOW_ENABLE_LOCAL_TRIAGE", "false")
    r = processar(api, recibo)
    assert r.status_code == 403
    assert r.json()["detail"]["codigo"] == "PROCESSAMENTO_DESABILITADO"
    assert not api.servico.chamadas
    assert not api.storage.reads


def test_flag_uploads_desligada_bloqueia_processamento(api, monkeypatch):
    recibo = enviar(api)
    monkeypatch.setenv("MEDIFLOW_ENABLE_LOCAL_UPLOADS", "false")
    r = processar(api, recibo)
    assert r.status_code == 403
    assert not api.servico.chamadas


def test_ambiente_nao_desenvolvimento_bloqueia(api, monkeypatch):
    recibo = enviar(api)
    monkeypatch.setenv("MEDIFLOW_ENV", "production")
    r = processar(api, recibo)
    assert r.status_code == 403
    assert not api.servico.chamadas


def test_sem_adaptador_configurado_falha_fechada(api):
    recibo = enviar(api)
    api.app.dependency_overrides.pop(obter_servico_triagem)
    api.storage.reads.clear()
    r = processar(api, recibo)
    assert r.status_code == 503
    assert r.json()["detail"]["codigo"] == "TRIAGEM_NAO_CONFIGURADA"
    assert not api.storage.reads


def test_manifesto_nao_encontrado_retorna_404(api):
    r = api.client.post("/v1/triagens/arquivos/DOC-001/" + "a" * 32 + "/processar")
    assert r.status_code == 404
    assert r.json()["detail"]["codigo"] == "REGISTRO_NAO_ENCONTRADO"
    assert not api.servico.chamadas


def test_manifesto_invalido_retorna_502(api):
    recibo = enviar(api)
    chave = recibo["registro_metadados"]["chave_metadados"]
    api.storage.objetos[chave] = b"{json invalido"
    r = processar(api, recibo)
    assert r.status_code == 502
    assert r.json()["detail"]["codigo"] == "REGISTRO_INVALIDO"
    assert not api.servico.chamadas


def test_manifesto_com_id_de_outro_documento_rejeitado(api):
    recibo = enviar(api)
    alterar_manifesto(api, recibo, lambda dados: dados.update(documento_id="DOC-OUTRO"))
    r = processar(api, recibo)
    assert r.status_code == 502
    assert r.json()["detail"]["codigo"] == "REGISTRO_INCONSISTENTE"
    assert not api.servico.chamadas


def test_manifesto_com_bucket_divergente_rejeitado(api):
    recibo = enviar(api)
    alterar_manifesto(api, recibo, lambda dados: dados["armazenamento_original"].update(bucket="outro-bucket"))
    r = processar(api, recibo)
    assert r.status_code == 502
    assert not api.servico.chamadas


def test_nome_original_com_extension_divergente_rejeitado(api):
    recibo = enviar(api)
    alterar_manifesto(api, recibo, lambda dados: dados["entrada"].update(nome_arquivo="laudo.png"))
    r = processar(api, recibo)
    assert r.status_code == 502
    assert r.json()["detail"]["codigo"] == "REGISTRO_INCONSISTENTE"
    assert not api.servico.chamadas


def test_original_com_hash_incorreto_bloqueia_servico(api):
    recibo = enviar(api)
    api.storage.objetos[recibo["armazenamento_original"]["chave_original"]] = b"CORROMPIDO"
    r = processar(api, recibo)
    assert r.status_code == 502
    assert r.json()["detail"]["codigo"] == "INTEGRIDADE_ORIGINAL_INVALIDA"
    assert not api.servico.chamadas


def test_original_mesmo_tamanho_com_hash_divergente_bloqueia_servico(api):
    recibo = enviar(api)
    chave = recibo["armazenamento_original"]["chave_original"]
    dados = bytearray(api.storage.objetos[chave])
    dados[-1] ^= 1
    api.storage.objetos[chave] = bytes(dados)
    r = processar(api, recibo)
    assert r.status_code == 502
    assert r.json()["detail"]["codigo"] == "INTEGRIDADE_ORIGINAL_INVALIDA"
    assert not api.servico.chamadas


def test_original_com_tamanho_incorreto_bloqueia_servico(api):
    recibo = enviar(api)
    # O hash continua o mesmo, mas o tamanho declarado passa a divergir.
    alterar_manifesto(api, recibo, lambda dados: dados.update(tamanho_bytes=dados["tamanho_bytes"] + 1))
    r = processar(api, recibo)
    assert r.status_code == 502
    assert r.json()["detail"]["codigo"] == "INTEGRIDADE_ORIGINAL_INVALIDA"
    assert not api.servico.chamadas


def test_original_indisponivel_nao_expoe_excecao(api):
    recibo = enviar(api)
    api.storage.fail_prefix = "originais/"
    r = processar(api, recibo)
    assert r.status_code == 502
    assert r.json()["detail"]["codigo"] == "ORIGINAL_INDISPONIVEL"
    assert "SEGREDO_QUE_NAO_DEVE_APARECER" not in r.text
    assert not api.servico.chamadas


@pytest.mark.parametrize("documento_id,arquivo_id", [
    ("../DOC-001", "a" * 32),
    ("DOC-001", "a" * 31),
    ("DOC-001", "x" * 32),
])
def test_id_invalido_retorna_422_sem_servico(api, documento_id, arquivo_id):
    r = api.client.post(f"/v1/triagens/arquivos/{documento_id}/{arquivo_id}/processar")
    assert r.status_code in {404, 422}  # caminhos normalizados podem nao corresponder
    assert not api.servico.chamadas


def test_erro_da_orquestracao_sanitizado(api):
    recibo = enviar(api)
    api.servico.falha = FalhaOrquestracao("SENHA_FALSA", "extracao")
    r = processar(api, recibo)
    assert r.status_code == 502
    assert r.json()["detail"]["codigo"] == "EXTRACAO_INDISPONIVEL"
    assert "SENHA_FALSA" not in r.text


def test_excecao_de_servico_sanitizada(api):
    recibo = enviar(api)
    api.servico.falha = RuntimeError("TOKEN_FALSO_NAO_REVELAR")
    r = processar(api, recibo)
    assert r.status_code == 502
    assert r.json()["detail"]["codigo"] == "PROCESSAMENTO_INDISPONIVEL"
    assert "TOKEN_FALSO_NAO_REVELAR" not in r.text


def test_retorno_de_servico_invalido_rejeitado(api):
    recibo = enviar(api)
    api.servico.retorno_forcado = {"inventado": True}
    r = processar(api, recibo)
    assert r.status_code == 502
    assert r.json()["detail"]["codigo"] == "PROCESSAMENTO_INDISPONIVEL"


def test_resultado_com_documento_divergente_rejeitado(api):
    recibo = enviar(api)
    saida = json.loads((RAIZ / "exemplos/DOC-001_resultado.json").read_text(encoding="utf-8"))
    saida["documento_id"] = "DOC-OUTRO"
    api.servico.retorno_forcado = ResultadoTriagem.model_validate(saida)
    r = processar(api, recibo)
    assert r.status_code == 502
    assert r.json()["detail"]["codigo"] == "RESULTADO_INCONSISTENTE"


def test_resultado_sem_hash_coerente_rejeitado(api):
    recibo = enviar(api)
    saida = json.loads((RAIZ / "exemplos/DOC-001_resultado.json").read_text(encoding="utf-8"))
    saida["entrada"]["sha256"] = "a" * 64
    api.servico.retorno_forcado = ResultadoTriagem.model_validate(saida)
    r = processar(api, recibo)
    assert r.status_code == 502
    assert r.json()["detail"]["codigo"] == "RESULTADO_INCONSISTENTE"


def test_status_nao_terminal_rejeitado(api):
    recibo = enviar(api)
    saida = json.loads((RAIZ / "exemplos/DOC-001_resultado.json").read_text(encoding="utf-8"))
    saida["status"] = "processando"
    api.servico.retorno_forcado = ResultadoTriagem.model_validate(saida)
    r = processar(api, recibo)
    assert r.status_code == 502
    assert r.json()["detail"]["codigo"] == "RESULTADO_INCONSISTENTE"


def test_api_gera_schema_sem_publicar_em_app_atual(api):
    paths = api.client.get("/openapi.json").json()["paths"]
    path = "/v1/triagens/arquivos/{documento_id}/{arquivo_id}/processar"
    assert path in paths
    assert "post" in paths[path]
    # A entrega nao modifica app.py nem anuncia rota pronta sem adaptadores.
    assert path not in app_develop.openapi()["paths"]
