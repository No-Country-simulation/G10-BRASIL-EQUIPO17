
import hashlib

import pymupdf
import pytest

from mediflow.extraction.extractor import ExtratorPDF
from mediflow.extraction.port import DocumentoParaExtracao


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
        sha256=hashlib.sha256(conteudo).hexdigest(),
    )


def criar_pdf() -> bytes:
    pdf = pymupdf.open()
    pagina = pdf.new_page()
    pagina.insert_text((72, 72), "Documento sintético de teste")
    conteudo = pdf.tobytes()
    pdf.close()
    return conteudo


def test_extrator_pdf_retorna_contrato_neutro():
    extrator = ExtratorPDF()
    documento = criar_documento(criar_pdf())

    resultado = extrator.extrair(documento)

    assert resultado.documento_id == "DOC-001"
    assert resultado.tipo_documento == "outro_desconhecido"
    assert resultado.dados_extraidos.medicamentos == []


def test_extrator_pdf_rejeita_tipo_incorreto():
    extrator = ExtratorPDF()
    documento = criar_documento(b"conteudo", "image/png")

    with pytest.raises(ValueError, match="somente arquivos PDF"):
        extrator.extrair(documento)


def test_extrator_pdf_rejeita_pdf_sem_texto():
    pdf = pymupdf.open()
    pdf.new_page()
    conteudo = pdf.tobytes()
    pdf.close()

    extrator = ExtratorPDF()
    documento = criar_documento(conteudo)

    with pytest.raises(ValueError, match="extrair texto"):
        extrator.extrair(documento)
