
"""Adaptador inicial de extração documental em PDF.

Esta versão lê o texto, mas ainda não interpreta semanticamente
as informações médicas nem utiliza um modelo de IA.
"""

from mediflow_contracts.models import DadosExtraidos, ExtracaoIA

from mediflow.extraction.pdf_text import extrair_texto_pdf
from mediflow.extraction.port import DocumentoParaExtracao


class ExtratorPDF:
    """Lê PDFs e produz um resultado neutro compatível com o contrato."""

    def extrair(self, documento: DocumentoParaExtracao) -> ExtracaoIA:
        if documento.mime_type != "application/pdf":
            raise ValueError("O extrator aceita somente arquivos PDF.")

        texto = extrair_texto_pdf(documento.conteudo)

        if not texto:
            raise ValueError("Não foi possível extrair texto do PDF.")

        return ExtracaoIA(
            documento_id=documento.documento_id,
            tipo_documento="outro_desconhecido",
            dados_extraidos=DadosExtraidos(
                descricao_documento=(
                    "Texto extraído do PDF; interpretação semântica "
                    "ainda não realizada."
                )
            ),
        )
