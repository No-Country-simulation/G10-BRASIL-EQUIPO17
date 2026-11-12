"""H11/I1: guardas HTTP de processamento, sem OCI, Gemini ou I4 reais.

A fixture ``api`` vem dos testes existentes e monta o router APENAS numa
FastAPI isolada, com FakeOCI e servico de demonstracao. Nunca cria acesso publico.
"""

import pytest
from fastapi.testclient import TestClient

from mediflow.api.app import app as app_principal
from mediflow.api.triage_processing import obter_servico_triagem
from mediflow.api.uploads import armazenamento
from test_api_triage_processing import api, enviar, processar

ROTA = "/v1/triagens/arquivos/{documento_id}/{arquivo_id}/processar"


def _sem_efeitos_colaterais(api, resposta):
    assert resposta.status_code == 403, resposta.text
    assert api.storage.reads == []
    assert api.servico.chamadas == []


def test_h11_app_principal_nao_publica_endpoint_mesmo_com_flags(monkeypatch):
    monkeypatch.setenv("MEDIFLOW_ENV", "development")
    monkeypatch.setenv("MEDIFLOW_ENABLE_LOCAL_UPLOADS", "true")
    monkeypatch.setenv("MEDIFLOW_ENABLE_LOCAL_TRIAGE", "true")
    assert ROTA not in [getattr(rota, "path", None) for rota in app_principal.routes]
    with TestClient(app_principal) as client:
        resposta = client.post(
            "/v1/triagens/arquivos/DOC-001/" + "a" * 32 + "/processar"
        )
    assert resposta.status_code == 404


def test_h11_ambiente_nao_definido_bloqueia_mesmo_com_flags(api, monkeypatch):
    recibo = enviar(api)
    api.storage.reads.clear()
    monkeypatch.delenv("MEDIFLOW_ENV", raising=False)
    resposta = processar(api, recibo)
    _sem_efeitos_colaterais(api, resposta)
    assert resposta.json()["detail"]["codigo"] == "PROCESSAMENTO_DESABILITADO"


@pytest.mark.parametrize(
    "ambiente", ["production", "staging", "test", "", "development "],
    ids=["producao", "homologacao", "test", "vazio", "espaco-sufixo"],
)
def test_h11_ambiente_nao_autorizado_rejeita_antes_oci(api, monkeypatch, ambiente):
    recibo = enviar(api)
    api.storage.reads.clear()
    monkeypatch.setenv("MEDIFLOW_ENV", ambiente)
    _sem_efeitos_colaterais(api, processar(api, recibo))


@pytest.mark.parametrize(
    "valor", ["1", "yes", "on", "true ", ""],
    ids=["um", "yes", "on", "espaco-sufixo", "vazio"],
)
def test_h11_flag_triagem_so_aceita_true(api, monkeypatch, valor):
    recibo = enviar(api)
    api.storage.reads.clear()
    monkeypatch.setenv("MEDIFLOW_ENABLE_LOCAL_TRIAGE", valor)
    resposta = processar(api, recibo)
    _sem_efeitos_colaterais(api, resposta)
    assert resposta.json()["detail"]["codigo"] == "PROCESSAMENTO_DESABILITADO"


def test_h11_sem_flag_triagem_bloqueia(api, monkeypatch):
    recibo = enviar(api)
    api.storage.reads.clear()
    monkeypatch.delenv("MEDIFLOW_ENABLE_LOCAL_TRIAGE", raising=False)
    resposta = processar(api, recibo)
    _sem_efeitos_colaterais(api, resposta)
    assert resposta.json()["detail"]["codigo"] == "PROCESSAMENTO_DESABILITADO"


def test_h11_sem_flag_upload_bloqueia(api, monkeypatch):
    recibo = enviar(api)
    api.storage.reads.clear()
    monkeypatch.delenv("MEDIFLOW_ENABLE_LOCAL_UPLOADS", raising=False)
    resposta = processar(api, recibo)
    _sem_efeitos_colaterais(api, resposta)
    assert resposta.json()["detail"]["codigo"] == "UPLOAD_DESABILITADO"


def test_h11_guardas_antecedem_injecao_de_storage_e_servico(api, monkeypatch):
    chamadas = []

    def criar_storage():
        chamadas.append("storage")
        raise AssertionError("O storage nao deveria ser construido")

    def criar_servico():
        chamadas.append("servico")
        raise AssertionError("O servico nao deveria ser construido")

    api.app.dependency_overrides[armazenamento] = criar_storage
    api.app.dependency_overrides[obter_servico_triagem] = criar_servico
    monkeypatch.setenv("MEDIFLOW_ENABLE_LOCAL_TRIAGE", "false")
    resposta = api.client.post(
        "/v1/triagens/arquivos/DOC-001/" + "a" * 32 + "/processar"
    )
    assert resposta.status_code == 403
    assert chamadas == []


def test_h11_sem_servico_homologado_retorna_503_antes_de_ler_oci(api):
    recibo = enviar(api)
    api.storage.reads.clear()
    del api.app.dependency_overrides[obter_servico_triagem]
    resposta = processar(api, recibo)
    assert resposta.status_code == 503
    assert resposta.json()["detail"]["codigo"] == "TRIAGEM_NAO_CONFIGURADA"
    assert api.storage.reads == []
    assert api.servico.chamadas == []


def test_h11_processamento_local_apenas_com_fakes_explicitos(api):
    recibo = enviar(api)
    resposta = processar(api, recibo)
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["armazenamento_oci"]["status"] == "pendente"
    assert len(api.servico.chamadas) == 1
