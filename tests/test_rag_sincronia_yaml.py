import re
from pathlib import Path

import yaml

from mediflow.rag.carregador import PASTA_PADRAO, carregar_fontes

RAIZ = Path(__file__).resolve().parents[1]


def _yaml(nome):
    return yaml.safe_load((RAIZ / "rules" / nome).read_text(encoding="utf-8"))


def _fichas():
    return {f.fonte_id: f for f in carregar_fontes()}


def test_toda_ficha_real_tem_origem_rastreavel():
    for caminho in PASTA_PADRAO.glob("*.md"):
        cabecalho = caminho.read_text(encoding="utf-8").split("---", 2)[1]
        assert "origem:" in cabecalho, f"{caminho.name} sem origem"


def test_fichas_de_roteamento_batem_com_o_yaml():
    dados = _yaml("roteamento.yaml")
    fichas = _fichas()
    for regra in dados["regras"]:
        ficha = fichas.get(regra["id"])
        assert ficha is not None, f"falta ficha para {regra['id']}: atualize a base"
        assert ficha.versao == str(dados["versao"]), f"versão divergente em {regra['id']}"
        esperado = "sim" if regra["requer_revisao_humana"] else "não"
        assert f"Requer revisão humana: {esperado}" in ficha.texto, (
            f"revisão humana divergente em {regra['id']}"
        )
    ids_yaml = {r["id"] for r in dados["regras"]}
    orfas = {i for i in fichas if re.fullmatch(r"R\d{3}", i)} - ids_yaml
    assert not orfas, f"fichas sem regra no YAML: {sorted(orfas)}"


def test_precedencia_da_ficha_bate_com_o_yaml():
    dados = _yaml("roteamento.yaml")
    ficha = _fichas()["ROTEAMENTO-PRECEDENCIA"]
    assert ", ".join(dados["precedencia"]) in ficha.texto


def test_fichas_de_validacao_batem_com_o_yaml():
    dados = _yaml("validacao.yaml")
    fichas = _fichas()
    for val in dados["validacoes"]:
        ficha = fichas.get(val["id"])
        assert ficha is not None, f"falta ficha para {val['id']}: atualize a base"
        assert ficha.versao == str(dados["versao"]), f"versão divergente em {val['id']}"
    ids_yaml = {v["id"] for v in dados["validacoes"]}
    orfas = {i for i in fichas if re.fullmatch(r"V\d{3}", i)} - ids_yaml
    assert not orfas, f"fichas sem validação no YAML: {sorted(orfas)}"


def test_campos_minimos_da_ficha_batem_com_o_yaml():
    dados = _yaml("validacao.yaml")
    ficha = _fichas()["CAMPOS-MINIMOS"]
    for categoria, campos in dados["campos_minimos_por_categoria"].items():
        for campo in campos:
            assert campo in ficha.texto, f"campo {campo} ({categoria}) ausente na ficha"
