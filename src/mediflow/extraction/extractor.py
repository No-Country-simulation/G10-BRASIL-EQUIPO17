
"""Funções e adaptadores para extração documental."""

import json

from mediflow_contracts.models import (
    DadosExtraidos,
    EntradaTexto,
    ExtracaoIA,
)

from mediflow.extraction.pdf_text import extrair_texto_pdf
from mediflow.extraction.port import DocumentoParaExtracao


class ExtratorPDF:
    """Lê PDFs e produz um resultado compatível com o contrato."""

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


def validar_extracao(
    documento_id: str,
    resposta_modelo: str,
) -> ExtracaoIA:
    """Valida a resposta JSON do modelo usando o contrato ExtracaoIA."""

    try:
        dados = json.loads(resposta_modelo)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "A resposta do modelo não é um JSON válido."
        ) from exc

    if not isinstance(dados, dict):
        raise ValueError("A resposta do modelo deve ser um objeto JSON.")

    if dados.get("documento_id") != documento_id:
        raise ValueError(
            "O documento_id da resposta não corresponde à entrada."
        )

    return ExtracaoIA.model_validate(dados)


def preparar_entrada(entrada: EntradaTexto) -> dict:
    """Prepara os dados para serem enviados ao modelo de IA."""

    return {
        "documento_id": entrada.documento_id,
        "documento_texto": entrada.documento_texto,
        "instrucao": (
            "Extraia somente informações presentes no documento. "
            "Não invente dados. Marque campos ausentes ou ilegíveis "
            "conforme o contrato de extração."
        ),
    }
