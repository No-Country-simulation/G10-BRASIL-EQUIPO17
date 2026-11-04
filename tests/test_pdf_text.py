
from io import BytesIO

import pymupdf
import pytest
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from mediflow.extraction.pdf_text import (
    extrair_texto_imagem,
    extrair_texto_pdf,
)


def criar_pdf_digital():
    """Cria um PDF fictício com texto selecionável."""
    documento = pymupdf.open()
    pagina = documento.new_page()
    pagina.insert_text(
        (72, 72),
        "Documento ficticio para teste de extracao.",
    )

    conteudo = documento.tobytes()
    documento.close()

    return conteudo


def test_extrair_texto_pdf_digital():
    conteudo = criar_pdf_digital()

    resultado = extrair_texto_pdf(conteudo)

    assert "Documento ficticio" in resultado
    assert "teste de extracao" in resultado


def test_extrair_texto_pdf_vazio():
    with pytest.raises(ValueError, match="conteúdo do PDF está vazio"):
        extrair_texto_pdf(b"")


def test_extrair_texto_pdf_invalido():
    with pytest.raises(ValueError, match="Não foi possível abrir o PDF"):
        extrair_texto_pdf(b"conteudo que nao e um PDF")


def test_extrair_texto_imagem_vazia():
    with pytest.raises(ValueError, match="conteúdo da imagem está vazio"):
        extrair_texto_imagem(b"")


def test_extrair_texto_imagem_invalida():
    with pytest.raises(ValueError, match="Não foi possível abrir a imagem"):
        extrair_texto_imagem(b"conteudo que nao e uma imagem")


def test_extrair_texto_imagem_formato_nao_suportado():
    buffer = BytesIO()
    Image.new("RGB", (100, 100)).save(buffer, format="BMP")

    with pytest.raises(ValueError, match="Formato de imagem não suportado"):
        extrair_texto_imagem(buffer.getvalue())


def criar_imagem_com_texto(formato="PNG"):
    """Gera uma imagem fictícia contendo texto."""
    imagem = Image.new("RGB", (1200, 300), color="white")

    desenho = ImageDraw.Draw(imagem)
    fonte = ImageFont.load_default(size=48)

    desenho.text(
        (40, 100),
        "DOCUMENTO FICTICIO PARA TESTE",
        fill="black",
        font=fonte,
    )

    buffer = BytesIO()
    imagem.save(buffer, format=formato)

    return buffer.getvalue()


def criar_pdf_digitalizado():
    """Gera um PDF contendo uma imagem com texto."""
    imagem = criar_imagem_com_texto("PNG")

    buffer = BytesIO()
    documento = canvas.Canvas(buffer, pagesize=(600, 150))

    documento.drawImage(
        ImageReader(BytesIO(imagem)),
        0,
        0,
        width=600,
        height=150,
    )

    documento.save()
    return buffer.getvalue()

def criar_pdf_com_duas_paginas():
    """Cria um PDF fictício com texto em duas páginas."""
    documento = pymupdf.open()

    pagina1 = documento.new_page()
    pagina1.insert_text((72, 72), "Texto exclusivo da primeira pagina.")

    pagina2 = documento.new_page()
    pagina2.insert_text((72, 72), "Texto exclusivo da segunda pagina.")

    conteudo = documento.tobytes()
    documento.close()

    return conteudo


def test_ocr_imagem_png():
    conteudo = criar_imagem_com_texto("PNG")

    resultado = extrair_texto_imagem(conteudo)

    assert "DOCUMENTO FICTICIO" in resultado.upper()


def test_ocr_imagem_jpeg():
    conteudo = criar_imagem_com_texto("JPEG")

    resultado = extrair_texto_imagem(conteudo)

    assert "DOCUMENTO FICTICIO" in resultado.upper()


def test_ocr_pdf_digitalizado():
    conteudo = criar_pdf_digitalizado()

    resultado = extrair_texto_pdf(conteudo)

    assert "DOCUMENTO FICTICIO" in resultado.upper()


def test_extrair_texto_pdf_preserva_numero_das_paginas():
    conteudo = criar_pdf_com_duas_paginas()

    resultado = extrair_texto_pdf(conteudo)

    assert "[Página 1]" in resultado
    assert "[Página 2]" in resultado
    assert resultado.index("[Página 1]") < resultado.index(
        "Texto exclusivo da primeira pagina."
    )
    assert resultado.index("[Página 2]") < resultado.index(
        "Texto exclusivo da segunda pagina."
    )
