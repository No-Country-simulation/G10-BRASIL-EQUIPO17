"""Fronteira do RAG: consulta + recuperador substituível.

Nenhuma dependência de Gemini, OCI ou FastAPI deve existir neste módulo.
"""
from dataclasses import dataclass
from typing import Protocol

from mediflow_contracts.models import RecuperacaoRAG


@dataclass(frozen=True, slots=True)
class ConsultaRAG:
    """Pergunta enviada ao recuperador de referências."""

    texto: str
    limite: int = 3

    def __post_init__(self) -> None:
        if type(self.limite) is not int or not 1 <= self.limite <= 10:
            raise ValueError("limite deve ser um inteiro entre 1 e 10.")


class RecuperadorReferencias(Protocol):
    """Contrato a ser implementado pelo RAG real, com retorno Pydantic v0.1."""

    def buscar(self, consulta: ConsultaRAG) -> RecuperacaoRAG:
        ...


class RecuperadorSimulado:
    """Só exercita a interface. Nunca inventa fontes."""

    def buscar(self, consulta: ConsultaRAG) -> RecuperacaoRAG:
        return RecuperacaoRAG(status="nao_consultado")