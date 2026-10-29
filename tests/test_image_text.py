
from io import BytesIO

import pytest
from PIL import Image

from mediflow.extraction.pdf_text import extrair_texto_imagem


def criar_png() -> bytes:
    imagem = Image.new("RGB", (100, 100), "white")
    buffer = BytesIO()
    imagem.save(buffer, format="PNG")
    return buffer.getvalue()


def test_extrair_texto_de_imagem_png(monkeypatch):
    def ocr_simulado(imagem, lang):
        assert lang == "por"
        return "Texto de teste"

    monkeypatch.setattr(
        "mediflow.extraction.pdf_text.pytesseract.image_to_string",
        ocr_simulado,
    )

    assert extrair_texto_imagem(criar_png()) == "Texto de teste"


def test_rejeitar_imagem_vazia():
    with pytest.raises(ValueError, match="vazio"):
        extrair_texto_imagem(b"")


def test_rejeitar_conteudo_que_nao_seja_imagem():
    with pytest.raises(ValueError, match="Não foi possível abrir"):
        extrair_texto_imagem(b"conteudo invalido")


def test_rejeitar_formato_de_imagem_nao_suportado():
    buffer = BytesIO()
    Image.new("RGB", (10, 10), "white").save(buffer, format="BMP")

    with pytest.raises(ValueError, match="não suportado"):
        extrair_texto_imagem(buffer.getvalue())
