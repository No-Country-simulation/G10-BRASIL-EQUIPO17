
"""Extração de texto de PDFs e imagens com OCR quando necessário."""

from io import BytesIO

import pymupdf
import pytesseract
from PIL import Image, UnidentifiedImageError


def extrair_texto_imagem(conteudo: bytes) -> str:
    """Extrai texto de imagens PNG e JPEG usando OCR."""
    if not conteudo:
        raise ValueError("O conteúdo da imagem está vazio.")

    try:
        with Image.open(BytesIO(conteudo)) as imagem:
            if imagem.format not in {"PNG", "JPEG"}:
                raise ValueError("Formato de imagem não suportado.")

            return pytesseract.image_to_string(
                imagem,
                lang="por",
            ).strip()
    except UnidentifiedImageError as exc:
        raise ValueError("Não foi possível abrir a imagem.") from exc


def extrair_texto_pdf(conteudo: bytes) -> str:
    """Extrai texto de PDFs digitais e digitalizados."""
    if not conteudo:
        raise ValueError("O conteúdo do PDF está vazio.")

    try:
        documento = pymupdf.open(
            stream=conteudo,
            filetype="pdf",
        )
    except Exception as exc:
        raise ValueError("Não foi possível abrir o PDF.") from exc

    paginas_texto = []

    try:
        for pagina in documento:
            texto = pagina.get_text().strip()

            if not texto:
                pixmap = pagina.get_pixmap(dpi=200)
                imagem = Image.open(
                    BytesIO(pixmap.tobytes("png"))
                )
                texto = pytesseract.image_to_string(
                    imagem,
                    lang="por",
                ).strip()

            paginas_texto.append(texto)
    finally:
        documento.close()

    return "\n".join(paginas_texto).strip()

