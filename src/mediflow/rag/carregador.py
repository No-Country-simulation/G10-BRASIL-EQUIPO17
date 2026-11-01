"""Carrega as fontes da base de conhecimento (arquivos .md com cabeçalho simples)."""
from pathlib import Path

from mediflow.rag.busca import FonteDocumento, RecuperadorPorPalavras

PASTA_PADRAO = Path(__file__).parent / "base_conhecimento"
CAMPOS_OBRIGATORIOS = ("fonte_id", "titulo", "versao")


def _ler_ficha(caminho: Path) -> FonteDocumento:
    bruto = caminho.read_text(encoding="utf-8")
    partes = bruto.split("---", 2)
    if len(partes) != 3 or partes[0].strip():
        raise ValueError(f"ficha inválida ({caminho.name}): cabeçalho ausente")
    meta = {}
    for linha in partes[1].strip().splitlines():
        chave, _, valor = linha.partition(":")
        meta[chave.strip()] = valor.strip()
    faltando = [c for c in CAMPOS_OBRIGATORIOS if not meta.get(c)]
    if faltando:
        raise ValueError(f"ficha inválida ({caminho.name}): faltam {', '.join(faltando)}")
    texto = partes[2].strip()
    if not texto:
        raise ValueError(f"ficha inválida ({caminho.name}): texto vazio")
    return FonteDocumento(
        fonte_id=meta["fonte_id"],
        titulo=meta["titulo"],
        texto=texto,
        versao=meta["versao"],
        url=meta.get("url") or None,
    )


def carregar_fontes(pasta: Path = PASTA_PADRAO) -> list[FonteDocumento]:
    if not pasta.is_dir():
        raise FileNotFoundError(f"pasta da base de conhecimento não encontrada: {pasta}")
    fontes = [_ler_ficha(p) for p in sorted(pasta.glob("*.md"))]
    ids = [f.fonte_id for f in fontes]
    repetidos = sorted({i for i in ids if ids.count(i) > 1})
    if repetidos:
        raise ValueError(f"fonte_id repetido: {', '.join(repetidos)}")
    return fontes


def criar_recuperador_padrao() -> RecuperadorPorPalavras:
    """Ponto de entrada para os outros módulos: recuperador com a base oficial."""
    return RecuperadorPorPalavras(carregar_fontes())
