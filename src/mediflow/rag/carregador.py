"""Carrega as fontes da base de conhecimento (arquivos .md com cabeçalho simples)."""
from pathlib import Path

from mediflow.rag.busca import FonteDocumento

PASTA_PADRAO = Path(__file__).parent / "base_conhecimento"


def _ler_ficha(caminho: Path) -> FonteDocumento:
    bruto = caminho.read_text(encoding="utf-8")
    _, cabecalho, corpo = bruto.split("---", 2)
    meta = {}
    for linha in cabecalho.strip().splitlines():
        chave, _, valor = linha.partition(":")
        meta[chave.strip()] = valor.strip()
    return FonteDocumento(
        fonte_id=meta["fonte_id"],
        titulo=meta["titulo"],
        texto=corpo.strip(),
        versao=meta.get("versao") or None,
        url=meta.get("url") or None,
    )


def carregar_fontes(pasta: Path = PASTA_PADRAO) -> list[FonteDocumento]:
    return [_ler_ficha(p) for p in sorted(pasta.glob("*.md"))]