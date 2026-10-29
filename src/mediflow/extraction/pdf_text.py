
"""Extração de texto de PDFs digitais e digitalizados."""

from io import BytesIO

import pymupdf
import pytesseract
from PIL import Image


def extrair_texto_pdf(conteudo: bytes) -> str:
    """Extrai texto de um PDF, usando OCR quando necessário."""
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
                imagem_bytes = pixmap.tobytes("png")

                imagem = Image.open(BytesIO(imagem_bytes))
                texto = pytesseract.image_to_string(
                    imagem,
                    lang="por",
                ).strip()

            paginas_texto.append(texto)
    finally:
        documento.close()

    return "\n".join(paginas_texto).strip()
