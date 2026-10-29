
import pytest
from unittest.mock import MagicMock, patch

from mediflow.extraction.gemini_extractor import ExtratorGemini
from mediflow_contracts.models import EntradaTexto


def criar_entrada():
    return EntradaTexto(
        documento_id="doc-123",
        canal_origem="teste",
        documento_texto="Documento fictício para teste.",
    )


def test_extrator_rejeita_api_key_ausente(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        ExtratorGemini()


def test_extrator_envia_texto_e_valida_resposta(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "chave-ficticia")

    resposta_json = {
        "contrato_versao": "0.1",
        "documento_id": "doc-123",
        "tipo_documento": "outro_desconhecido",
        "dados_extraidos": {},
    }

    resposta = MagicMock()
    resposta.text = __import__("json").dumps(resposta_json)

    cliente_mock = MagicMock()
    cliente_mock.models.generate_content.return_value = resposta

    with patch(
        "mediflow.extraction.gemini_extractor.genai.Client",
        return_value=cliente_mock,
    ):
        extrator = ExtratorGemini()
        resultado = extrator.extrair_texto(criar_entrada())

    assert resultado.documento_id == "doc-123"
    cliente_mock.models.generate_content.assert_called_once()


def test_extrator_rejeita_resposta_sem_texto(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "chave-ficticia")

    resposta = MagicMock()
    resposta.text = None

    cliente_mock = MagicMock()
    cliente_mock.models.generate_content.return_value = resposta

    with patch(
        "mediflow.extraction.gemini_extractor.genai.Client",
        return_value=cliente_mock,
    ):
        extrator = ExtratorGemini()

        with pytest.raises(ValueError, match="resposta vazia"):
            extrator.extrair_texto(criar_entrada())



from mediflow.extraction.port import DocumentoParaExtracao, ExtratorDocumento


def criar_documento(mime_type="text/plain", conteudo=b"Documento ficticio"):
    return DocumentoParaExtracao(
        documento_id="doc-123",
        arquivo_id="arquivo-123",
        nome_original="documento.txt",
        mime_type=mime_type,
        conteudo=conteudo,
        sha256="hash-ficticio",
    )



def test_extrator_gemini_implementa_interface(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "chave-ficticia")

    with patch(
        "mediflow.extraction.gemini_extractor.genai.Client"
    ):
        extrator = ExtratorGemini()

    assert callable(getattr(extrator, "extrair", None))



def test_extrator_rejeita_tipo_nao_suportado(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "chave-ficticia")

    with patch(
        "mediflow.extraction.gemini_extractor.genai.Client"
    ):
        extrator = ExtratorGemini()

    with pytest.raises(ValueError, match="Tipo de arquivo não suportado"):
        extrator.extrair(
            criar_documento(mime_type="application/pdf", conteudo=b"%PDF")
        )


def test_extrator_rejeita_texto_utf8_invalido(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "chave-ficticia")

    with patch(
        "mediflow.extraction.gemini_extractor.genai.Client"
    ):
        extrator = ExtratorGemini()

    with pytest.raises(ValueError, match="UTF-8"):
        extrator.extrair(
            criar_documento(conteudo=b"\xff\xfe")
        )
