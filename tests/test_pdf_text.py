from io import BytesIO

import pymupdf
import pytesseract
from PIL import Image, ImageDraw
import pymupdf
import pytest

from mediflow.extraction.pdf_text import extrair_texto_pdf


def criar_pdf_com_texto() -> bytes:
    documento = pymupdf.open()
    pagina = documento.new_page()
    pagina.insert_text((72, 72), "Receita médica de teste")
    conteudo = documento.tobytes()
    documento.close()
    return conteudo


def test_extrai_texto_de_pdf_digital():
    conteudo = criar_pdf_com_texto()

    texto = extrair_texto_pdf(conteudo)

    assert "Receita médica de teste" in texto


def test_rejeita_pdf_vazio():
    with pytest.raises(ValueError, match="vazio"):
        extrair_texto_pdf(b"")


def test_rejeita_arquivo_que_nao_e_pdf():
    with pytest.raises(ValueError, match="abrir o PDF"):
        extrair_texto_pdf(b"isto nao e um PDF")

def test_extrai_texto_de_pdf_digitalizado():
    imagem = Image.new("RGB", (1200, 300), "white")
    desenho = ImageDraw.Draw(imagem)
    desenho.text(
        (40, 100),
        "Documento de teste para OCR",
        fill="black",
        font_size=48,
    )

    buffer_imagem = BytesIO()
    imagem.save(buffer_imagem, format="PNG")

    documento = pymupdf.open()
    pagina = documento.new_page(width=600, height=150)
    pagina.insert_image(
        pagina.rect,
        stream=buffer_imagem.getvalue(),
    )
    conteudo_pdf = documento.tobytes()
    documento.close()

    texto = extrair_texto_pdf(conteudo_pdf)

    assert "Documento de teste para OCR" in texto
