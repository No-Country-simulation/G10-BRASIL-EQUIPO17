
from io import BytesIO

import pymupdf
import pytest

from mediflow.extraction.pdf_extractor import ExtratorPDF
from mediflow.extraction.port import DocumentoParaExtracao


def criar_pdf(texto: str) -> bytes:
    """Cria um PDF simples para os testes."""
    documento = pymupdf.open()
    pagina = documento.new_page()
    pagina.insert_text((72, 72), texto)
    conteudo = documento.tobytes()
    documento.close()
    return conteudo


def criar_documento(
    conteudo: bytes,
    mime_type: str = "application/pdf",
) -> DocumentoParaExtracao:
    return DocumentoParaExtracao(
        documento_id="DOC-001",
        arquivo_id="ARQ-001",
        nome_original="documento.pdf",
        mime_type=mime_type,
        conteudo=conteudo,
        sha256="a" * 64,
    )


def test_extrair_pdf_com_texto():
    documento = criar_documento(
        criar_pdf("Documento de teste.")
    )

    resultado = ExtratorPDF().extrair(documento)

    assert resultado.documento_id == "DOC-001"
    assert resultado.tipo_documento == "outro_desconhecido"
    assert (
        resultado.dados_extraidos.descricao_documento
        == "Documento de teste."
    )


def test_rejeitar_formato_diferente_de_pdf():
    documento = criar_documento(
        b"conteudo",
        mime_type="image/png",
    )

    with pytest.raises(ValueError, match="somente arquivos PDF"):
        ExtratorPDF().extrair(documento)


def test_rejeitar_pdf_sem_texto():
    documento = criar_documento(b"")

    with pytest.raises(ValueError, match="conteúdo do PDF está vazio"):
        ExtratorPDF().extrair(documento)


def test_rejeitar_pdf_invalido():
    documento = criar_documento(b"isso nao e um PDF")

    with pytest.raises(ValueError, match="Não foi possível abrir o PDF"):
        ExtratorPDF().extrair(documento)
