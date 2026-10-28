"""Fronteira I1/I2: documento validado + extrator substituível.

Nenhuma dependência de Gemini, OCI ou FastAPI deve existir neste módulo.
"""
from dataclasses import dataclass
from typing import Protocol

from mediflow_contracts.models import DadosExtraidos, ExtracaoIA


@dataclass(frozen=True, slots=True)
class DocumentoParaExtracao:
    """Documento em memória vindo de uma origem cuja integridade foi conferida."""

    documento_id: str
    arquivo_id: str
    nome_original: str
    mime_type: str
    conteudo: bytes
    sha256: str


class ExtratorDocumento(Protocol):
    """Contrato a ser implementado pelo I2, com retorno Pydantic v0.1."""

    def extrair(self, documento: DocumentoParaExtracao) -> ExtracaoIA:
        ...


class ExtratorSimulado:
    """Só exercita a interface. Nunca interpreta o documento ou sugere diagnóstico."""

    def extrair(self, documento: DocumentoParaExtracao) -> ExtracaoIA:
        # Valores neutros: não usar como classificação real nem como prova de extração.
        return ExtracaoIA(
            documento_id=documento.documento_id,
            tipo_documento="outro_desconhecido",
            dados_extraidos=DadosExtraidos(),
        )
