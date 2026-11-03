"""Recuperador simples por palavras-chave (v1: sem IA, sem rede)."""
import re
import unicodedata
from dataclasses import dataclass

from mediflow_contracts.models import FonteRAG, RecuperacaoRAG

from mediflow.rag.port import ConsultaRAG


@dataclass(frozen=True, slots=True)
class FonteDocumento:
    """Uma fonte de referência da base de conhecimento."""

    fonte_id: str
    titulo: str
    texto: str
    versao: str | None = None
    url: str | None = None


def _normalizar(texto: str) -> set[str]:
    decomposto = unicodedata.normalize("NFD", texto.lower())
    sem_acento = "".join(c for c in decomposto if unicodedata.category(c) != "Mn")
    return {p for p in re.findall(r"[a-z0-9]+", sem_acento) if len(p) > 2}


def _trecho(texto: str, termos: set[str], tamanho: int = 200) -> str:
    """Devolve a linha da ficha com mais termos em comum com a consulta."""
    melhor = ""
    melhor_pontos = 0
    for linha in texto.splitlines():
        limpa = linha.strip().lstrip("#-* ").strip()
        if not limpa:
            continue
        pontos = len(termos & _normalizar(limpa))
        if pontos > melhor_pontos:
            melhor, melhor_pontos = limpa, pontos
    if not melhor:
        return texto.strip()[:tamanho]
    return melhor[:tamanho]


class RecuperadorPorPalavras:
    """Pontua cada fonte pelas palavras em comum com a consulta."""

    def __init__(self, fontes: list[FonteDocumento]) -> None:
        self._fontes = list(fontes)

    def buscar(self, consulta: ConsultaRAG) -> RecuperacaoRAG:
        try:
            termos = _normalizar(consulta.texto)
            pontuadas = []
            for fonte in self._fontes:
                pontos = len(termos & _normalizar(f"{fonte.titulo} {fonte.texto}"))
                if pontos > 0:
                    pontuadas.append((pontos, fonte))
            if not pontuadas:
                return RecuperacaoRAG(status="sem_resultados")
            pontuadas.sort(key=lambda p: p[0], reverse=True)
            fontes = [
                FonteRAG(
                    fonte_id=f.fonte_id,
                    titulo=f.titulo,
                    url=f.url,
                    versao=f.versao,
                    trecho_relevante=_trecho(f.texto, termos),
                )
                for _, f in pontuadas[: consulta.limite]
            ]
            return RecuperacaoRAG(status="consultado", fontes=fontes)
        except Exception:
            return RecuperacaoRAG(status="falha", erro_codigo="RAG_ERRO_BUSCA")