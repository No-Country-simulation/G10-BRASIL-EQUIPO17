"""Testes da rota de extração real sem chamadas ao Gemini ou credenciais Oracle."""

import os
from hashlib import sha256
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mediflow.api.app import app
from mediflow.api.uploads import armazenamento
from mediflow.api.extraction import extrator_gemini
from mediflow.extraction.port import DocumentoParaExtracao
from mediflow_contracts.models import DadosExtraidos, ExtracaoIA


PDF = (
    Path(__file__).resolve().parents[1]
    / "amostras/pdf/DOC-001_laudo_laboratorial_rotina.pdf"
).read_bytes()


class ArmazenamentoFake:
    bucket = "bucket-sintetico"

    def __init__(self):
        self.objetos = {}
        self.fail_download = False
        self.reads = []

    def upload_bytes(self, key, content, content_type="application/octet-stream"):
        self.objetos[key] = content
        return sha256(content).hexdigest()

    def download_bytes(self, key):
        self.reads.append(key)

        if self.fail_download and key.startswith("originais/"):
            raise RuntimeError("Chave privada fictícia, não divulgar")

        if key not in self.objetos:
            exc = LookupError("Não encontrado")
            exc.status = 404
            raise exc

        return self.objetos[key]


@pytest.fixture
def servico(monkeypatch):
    monkeypatch.setenv("MEDIFLOW_ENV", "development")
    monkeypatch.setenv("MEDIFLOW_ENABLE_LOCAL_UPLOADS", "true")

    fake = ArmazenamentoFake()
    app.dependency_overrides[armazenamento] = lambda: fake

    try:
        yield TestClient(app), fake
    finally:
        app.dependency_overrides.clear()


def enviar(client, data=PDF, name="laudo.pdf", mime="application/pdf",
           documento_id="DOC-001"):
    response = client.post(
        "/v1/triagens/arquivos",
        data={
            "documento_id": documento_id,
            "canal_origem": "teste_sintetico",
        },
        files={"arquivo": (name, data, mime)},
    )

    assert response.status_code == 201, response.text
    return response.json()


def extracao(client, recibo):
    return client.post(
        f"/v1/triagens/arquivos/{recibo['documento_id']}/"
        f"{recibo['arquivo_id']}/extracao"
    )


def test_extracao_real_retorna_contrato_valido(servico):
    client, fake = servico
    recibo = enviar(client)

    chamadas = []

    class ExtratorControle:
        def extrair(self, documento: DocumentoParaExtracao) -> ExtracaoIA:
            chamadas.append(documento)

            return ExtracaoIA(
                documento_id=documento.documento_id,
                tipo_documento="laudo_laboratorial",
                dados_extraidos=DadosExtraidos(),
            )

    app.dependency_overrides[extrator_gemini] = lambda: ExtratorControle()

    response = extracao(client, recibo)

    assert response.status_code == 200, response.text

    resultado = response.json()

    assert resultado["documento_id"] == recibo["documento_id"]
    assert resultado["tipo_documento"] == "laudo_laboratorial"
    assert resultado["contrato_versao"] == "0.1"

    assert len(chamadas) == 1
    assert chamadas[0].conteudo == PDF
    assert chamadas[0].mime_type == "application/pdf"
    assert chamadas[0].nome_original == "laudo.pdf"
    assert chamadas[0].sha256 == sha256(PDF).hexdigest()

    # A extração não deve criar ou modificar objetos no armazenamento.
    assert recibo["armazenamento_original"]["chave_original"] in fake.objetos


def test_extracao_com_original_alterado_bloqueia_extrator(servico):
    client, fake = servico
    recibo = enviar(client)

    chave_original = recibo["armazenamento_original"]["chave_original"]
    fake.objetos[chave_original] = b"CONTEUDO-ADULTERADO"

    class NaoExecutar:
        def extrair(self, documento):
            raise AssertionError("O extrator não deveria ser chamado")

    app.dependency_overrides[extrator_gemini] = lambda: NaoExecutar()

    response = extracao(client, recibo)

    assert response.status_code == 502
    assert response.json()["detail"]["codigo"] == "INTEGRIDADE_ORIGINAL_INVALIDA"


def test_extracao_original_indisponivel_retorna_erro_generico(servico):
    client, fake = servico
    recibo = enviar(client)

    fake.fail_download = True

    class NaoExecutar:
        def extrair(self, documento):
            raise AssertionError("O extrator não deveria ser chamado")

    app.dependency_overrides[extrator_gemini] = lambda: NaoExecutar()

    response = extracao(client, recibo)

    assert response.status_code == 502
    assert response.json()["detail"]["codigo"] == "ORIGINAL_INDISPONIVEL"
    assert "Chave privada" not in response.text


def test_extracao_manifesto_inexistente_retorna_404(servico):
    client, fake = servico

    class NaoExecutar:
        def extrair(self, documento):
            raise AssertionError("O extrator não deveria ser chamado")

    app.dependency_overrides[extrator_gemini] = lambda: NaoExecutar()

    response = client.post(
        "/v1/triagens/arquivos/DOC-001/"
        + "a" * 32
        + "/extracao"
    )

    assert response.status_code == 404
    assert response.json()["detail"]["codigo"] == "REGISTRO_NAO_ENCONTRADO"
    assert len(fake.reads) == 1
    assert fake.reads[0].startswith("metadados/")
    assert not any(chave.startswith("originais/") for chave in fake.reads)


def test_extracao_fora_do_dev_bloqueada(servico, monkeypatch):
    client, fake = servico
    recibo = enviar(client)

    monkeypatch.setenv("MEDIFLOW_ENABLE_LOCAL_UPLOADS", "false")

    response = extracao(client, recibo)

    assert response.status_code == 403
    assert not fake.reads


def test_extracao_retorno_invalido_retorna_502(servico):
    client, fake = servico
    recibo = enviar(client)

    class ExtratorInvalido:
        def extrair(self, documento):
            return {
                "documento_id": documento.documento_id,
                "tipo_documento": "tipo_inexistente",
                "dados_extraidos": {},
            }

    app.dependency_overrides[extrator_gemini] = lambda: ExtratorInvalido()

    response = extracao(client, recibo)

    assert response.status_code == 502
    assert response.json()["detail"]["codigo"] == "EXTRACAO_CONTRATO_INVALIDO"


def test_extracao_nao_permite_trocar_documento_id(servico):
    client, fake = servico
    recibo = enviar(client)

    class ExtratorIDIncorreto:
        def extrair(self, documento):
            return ExtracaoIA(
                documento_id="DOC-OUTRO",
                tipo_documento="outro_desconhecido",
                dados_extraidos=DadosExtraidos(),
            )

    app.dependency_overrides[extrator_gemini] = (
        lambda: ExtratorIDIncorreto()
    )

    response = extracao(client, recibo)

    assert response.status_code == 502
    assert (
        response.json()["detail"]["codigo"]
        == "EXTRACAO_DOCUMENTO_DIVERGENTE"
    )

def test_extracao_excecao_sem_vazamento_de_dados(servico):
    client, fake = servico
    recibo = enviar(client)

    class ExtratorComFalha:
        def extrair(self, documento):
            raise RuntimeError(
                "GEMINI_API_KEY=SENHA_FALSA_NUNCA_EXIBIR"
            )

    app.dependency_overrides[extrator_gemini] = (
        lambda: ExtratorComFalha()
    )

    response = extracao(client, recibo)

    assert response.status_code == 502
    assert response.json()["detail"]["codigo"] == "EXTRATOR_INDISPONIVEL"
    assert "SENHA_FALSA_NUNCA_EXIBIR" not in response.text


def test_extracao_rota_documentada_no_swagger(servico):
    client, fake = servico

    paths = client.get("/openapi.json").json()["paths"]

    assert (
        "/v1/triagens/arquivos/{documento_id}/{arquivo_id}/extracao"
        in paths
    )


@pytest.mark.skipif(
    not os.getenv("GEMINI_API_KEY"),
    reason="GEMINI_API_KEY não configurada",
)
def test_fluxo_api_com_gemini_real(servico):
    client, fake = servico

    recibo = enviar(client)

    response = extracao(client, recibo)

    assert response.status_code == 200, response.text

    resultado = ExtracaoIA.model_validate(response.json())

    assert resultado.documento_id == recibo["documento_id"]
    assert resultado.tipo_documento == "laudo_laboratorial"

    chave_original = recibo["armazenamento_original"]["chave_original"]
    assert chave_original in fake.objetos

    assert fake.reads
    assert chave_original in fake.reads