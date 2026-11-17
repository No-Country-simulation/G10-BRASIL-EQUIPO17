"""Valida a fronteira API/OCI/I2 sem Gemini e sem credenciais Oracle."""
from hashlib import sha256
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mediflow.api.app import app
from mediflow.api.uploads import armazenamento
from mediflow.api.extraction_preview import extrator_de_desenvolvimento
from mediflow.extraction.port import DocumentoParaExtracao, ExtratorSimulado
from mediflow_contracts.models import DadosExtraidos, ExtracaoIA

PDF = (Path(__file__).resolve().parents[1] / 'amostras/pdf/DOC-001_laudo_laboratorial_rotina.pdf').read_bytes()
PNG = (Path(__file__).resolve().parents[1] / 'amostras/imagens/DOC-005_receita_ilegivel.png').read_bytes()


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


def enviar(client, data=PDF, name="laudo.pdf", mime="application/pdf", documento_id="DOC-001"):
    response = client.post("/v1/triagens/arquivos", data={
        "documento_id": documento_id, "canal_origem": "teste_sintetico"
    }, files={"arquivo": (name, data, mime)})
    assert response.status_code == 201, response.text
    return response.json()


def preview(client, recibo):
    return client.get(f"/v1/triagens/arquivos/{recibo['documento_id']}/{recibo['arquivo_id']}/extracao-preview")


@pytest.mark.parametrize(
    "data,name,mime",
    [
        (PDF, "laudo.pdf", "application/pdf"),
        (PNG, "receita.png", "image/png"),
    ],
    ids=["pdf", "png"],
)

def test_preview_recupera_documento_da_oci_simulada_sem_afirmar_ia(servico, data, name, mime):
    client, fake = servico
    recibo = enviar(client, data=data, name=name, mime=mime)
    objetos_antes = dict(fake.objetos)
    response = preview(client, recibo)
    assert response.status_code == 200, response.text
    content = response.json()
    assert content["documento_id"] == recibo["documento_id"]
    assert content["arquivo_id"] == recibo["arquivo_id"]
    assert content["modo"] == "simulacao_tecnica"
    assert content["integridade_original"] == "confirmada"
    assert content["triagem_executada"] is False
    assert content["resultado_contrato"]["contrato_versao"] == "0.1"
    assert content["resultado_contrato"]["tipo_documento"] == "outro_desconhecido"
    assert content["resultado_contrato"]["dados_extraidos"]["paciente"]["nome"] is None
    assert "Simulacao" in content["aviso"]
    assert fake.objetos == objetos_antes   # Rota somente leitura; nada novo salvo.
    assert fake.reads == [
        recibo["registro_metadados"]["chave_metadados"],
        recibo["armazenamento_original"]["chave_original"],
    ]


def test_extrator_recebe_bytes_reais_e_metadados_do_manifesto(servico):
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

    app.dependency_overrides[extrator_de_desenvolvimento] = lambda: ExtratorControle()
    resp = preview(client, recibo)
    assert resp.status_code == 200, resp.text
    assert len(chamadas) == 1
    assert chamadas[0].conteudo == PDF
    assert chamadas[0].mime_type == "application/pdf"
    assert chamadas[0].nome_original == "laudo.pdf"
    assert chamadas[0].sha256 == sha256(PDF).hexdigest()
    # Rota permanece explicitamente de preview mesmo com extrator injetado.
    assert resp.json()["modo"] == "simulacao_tecnica"
    assert resp.json()["triagem_executada"] is False


def test_preview_com_original_alterado_bloqueia_extracao(servico):
    client, fake = servico
    recibo = enviar(client)
    fake.objetos[recibo["armazenamento_original"]["chave_original"]] = b"CONTEUDO-ADULTERADO"

    class NaoExecutar:
        def extrair(self, doc):
            raise AssertionError("Não deve chegar ao extrator sem SHA válido")

    app.dependency_overrides[extrator_de_desenvolvimento] = lambda: NaoExecutar()
    resp = preview(client, recibo)
    assert resp.status_code == 502
    assert resp.json()["detail"]["codigo"] == "INTEGRIDADE_ORIGINAL_INVALIDA"


def test_preview_original_indisponivel_erro_generico(servico):
    client, fake = servico
    recibo = enviar(client)
    fake.fail_download = True
    resp = preview(client, recibo)
    assert resp.status_code == 502
    assert resp.json()["detail"]["codigo"] == "ORIGINAL_INDISPONIVEL"
    assert "Chave privada" not in resp.text


def test_preview_original_nao_encontrado(servico):
    client, fake = servico
    recibo = enviar(client)
    del fake.objetos[recibo["armazenamento_original"]["chave_original"]]
    resp = preview(client, recibo)
    assert resp.status_code == 502
    assert resp.json()["detail"]["codigo"] == "ORIGINAL_INDISPONIVEL"


def test_preview_manifesto_inexistente_retorna_404(servico):
    client, fake = servico
    resp = client.get("/v1/triagens/arquivos/DOC-001/" + "a"*32 + "/extracao-preview")
    assert resp.status_code == 404
    assert resp.json()["detail"]["codigo"] == "REGISTRO_NAO_ENCONTRADO"


def test_preview_fora_do_dev_bloqueado(servico, monkeypatch):
    client, fake = servico
    recibo = enviar(client)
    monkeypatch.setenv("MEDIFLOW_ENABLE_LOCAL_UPLOADS", "false")
    resp = preview(client, recibo)
    assert resp.status_code == 403


def test_preview_extrator_retorna_formato_invalido(servico):
    client, fake = servico
    recibo = enviar(client)

    class Invalid:
        def extrair(self, doc):
            return {"documento_id": doc.documento_id, "tipo_documento": "inventado", "dados_extraidos": {}}

    app.dependency_overrides[extrator_de_desenvolvimento] = lambda: Invalid()
    resp = preview(client, recibo)
    assert resp.status_code == 502
    assert resp.json()["detail"]["codigo"] == "EXTRACAO_CONTRATO_INVALIDO"


def test_preview_extrator_nao_pode_trocar_documento_id(servico):
    client, fake = servico
    recibo = enviar(client)

    class WrongID:
        def extrair(self, doc):
            return ExtracaoIA(
                documento_id="DOC-OUTRO",
                tipo_documento="outro_desconhecido",
                dados_extraidos=DadosExtraidos(),
            )

    app.dependency_overrides[extrator_de_desenvolvimento] = lambda: WrongID()
    resp = preview(client, recibo)
    assert resp.status_code == 502
    assert resp.json()["detail"]["codigo"] == "EXTRACAO_DOCUMENTO_DIVERGENTE"


def test_preview_extrator_com_excecao_sem_vazamento(servico):
    client, fake = servico
    recibo = enviar(client)

    class Fail:
        def extrair(self, doc):
            raise RuntimeError("GEMINI_API_KEY=SENHA_FALSA_NUNCA_EXIBIR")

    app.dependency_overrides[extrator_de_desenvolvimento] = lambda: Fail()
    resp = preview(client, recibo)
    assert resp.status_code == 502
    assert resp.json()["detail"]["codigo"] == "EXTRATOR_INDISPONIVEL"
    assert "SENHA_FALSA_NUNCA_EXIBIR" not in resp.text


def test_preview_invalido_nao_requisita_oci(servico):
    client, fake = servico
    resp = client.get("/v1/triagens/arquivos/DOC-001/invalido/extracao-preview")
    assert resp.status_code == 422
    assert not fake.reads


def test_preview_rota_documentada_no_swagger(servico):
    client, fake = servico
    paths = client.get("/openapi.json").json()["paths"]
    assert "/v1/triagens/arquivos/{documento_id}/{arquivo_id}/extracao-preview" in paths


def test_extrator_simulado_nao_faz_inferencia_sem_midia():
    fake_doc = DocumentoParaExtracao(
        documento_id="DOC-001", arquivo_id="a"*32,
        nome_original="nao-inferir.png", mime_type="image/png",
        conteudo=b"CONTEUDO-ALEATORIO", sha256="0"*64,
    )
    ext = ExtratorSimulado().extrair(fake_doc)
    assert ext.tipo_documento == "outro_desconhecido"
    assert ext.dados_extraidos.medicamentos == []
    assert ext.evidencias == []
