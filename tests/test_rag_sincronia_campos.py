import re
import unicodedata
from pathlib import Path

import yaml

from mediflow.rag.carregador import carregar_fontes

RAIZ = Path(__file__).resolve().parents[1]

ROTULOS_REGRA = [
    "condicao",
    "destino",
    "requer revisao humana",
    "prioridade",
    "justificativa da regra",
]
ROTULOS_VALIDACAO = ["condicao", "nivel", "encaminhamento"]
FIM_DA_FICHA = "uso no rag"


def _norm(texto):
    decomposto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn")


def _tokens(texto):
    return set(re.findall(r"[a-z0-9]+", _norm(texto)))


def _yaml(nome):
    return yaml.safe_load((RAIZ / "rules" / nome).read_text(encoding="utf-8"))


def _fichas():
    return {f.fonte_id: f for f in carregar_fontes()}


def _segmento(texto, rotulo, todos):
    normalizado = _norm(texto)
    outros = [r for r in todos if r != rotulo] + [FIM_DA_FICHA]
    parada = "|".join(re.escape(o) + ":" for o in outros)
    padrao = re.escape(rotulo) + r":\s*(.*?)(?=(?:" + parada + r")|\Z)"
    achado = re.search(padrao, normalizado, re.S)
    assert achado, f"rotulo '{rotulo}' ausente na ficha"
    return achado.group(1)


def _confere(ficha, id_, campo, valor_yaml, rotulo, rotulos):
    segmento = _segmento(ficha.texto, rotulo, rotulos)
    faltam = _tokens(str(valor_yaml)) - _tokens(segmento)
    assert not faltam, (
        f"{id_}: '{campo}' diverge do YAML ({valor_yaml}); "
        f"palavras ausentes no trecho '{rotulo}' da ficha: {sorted(faltam)}. "
        f"Atualize a ficha."
    )


def test_campos_das_regras_batem_com_o_yaml():
    fichas = _fichas()
    for regra in _yaml("roteamento.yaml")["regras"]:
        ficha = fichas[regra["id"]]
        for campo, rotulo in [
            ("condicao", "condicao"),
            ("destino", "destino"),
            ("prioridade", "prioridade"),
            ("justificativa", "justificativa da regra"),
        ]:
            _confere(ficha, regra["id"], campo, regra[campo], rotulo, ROTULOS_REGRA)


def test_campos_das_validacoes_batem_com_o_yaml():
    fichas = _fichas()
    for val in _yaml("validacao.yaml")["validacoes"]:
        ficha = fichas[val["id"]]
        for campo, rotulo in [
            ("condicao", "condicao"),
            ("nivel", "nivel"),
            ("encaminhamento", "encaminhamento"),
        ]:
            _confere(ficha, val["id"], campo, val[campo], rotulo, ROTULOS_VALIDACAO)


def test_comparador_detecta_valor_diferente():
    trecho = "fila prioritaria de avaliacao humana"
    assert _tokens("fila_prioritaria_avaliacao_humana") <= _tokens(trecho)
    assert not (_tokens("auditoria_humana") <= _tokens(trecho))
