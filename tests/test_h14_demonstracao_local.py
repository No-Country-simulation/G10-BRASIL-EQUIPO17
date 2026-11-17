"""Testes H14 da evidencia dos tres cenarios, sem Gemini/OCI reais."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mediflow.api.app_demo_local import cliente_fakeoci
from scripts import homologar_h14_demo_local as h14


def test_h14_tres_cenarios_e_limites_de_simulacao():
    relatorio = h14.executar_h14()
    assert relatorio["criterio"] == "H14"
    assert relatorio["status_h14"] == "aprovado_com_simulacao"
    assert relatorio["componentes"]["gemini_real"] is False
    assert relatorio["componentes"]["oci_real"] is False
    assert relatorio["componentes"]["streamlit_executado"] is False
    assert len(relatorio["git_commit_base"]) == 40
    resultados = {item["documento_id"]: item for item in relatorio["cenarios"]}
    assert set(resultados) == set(h14.CENARIOS)
    for doc_id, dados in resultados.items():
        esperado = h14.CENARIOS[doc_id]
        assert dados["teste_id"] == f"H14-{doc_id}"
        assert dados["regra"] == esperado["regra"]
        assert dados["destino"] == esperado["destino"]
        assert dados["revisao_humana"] is esperado["revisao"]
        assert dados["status_resultado"] == esperado["status"]
        assert dados["http_upload"] == 201
        assert dados["http_processamento"] == 200
        assert dados["persistencia"] == "fakeoci_memoria_verificada"


def test_h14_nao_vaza_documento_nem_chaves(tmp_path: Path):
    relatorio = h14.executar_h14()
    destino = h14.salvar_relatorio(relatorio, tmp_path / "h14.json")
    texto = destino.read_text(encoding="utf-8")
    dados = json.loads(texto)
    assert dados["criterio"] == "H14"
    for proibido in (
        "Marina Lacerda", "Carlos Almeida", "Fernanda Oliveira",
        "chave_original", "chave_resultado", "chave_historico",
        "arquivo_id", "GEMINI_API_KEY", "OCID", "extracao_ia",
    ):
        assert proibido not in texto


def test_h14_nao_modifica_fakeoci_preexistente():
    copia = dict(cliente_fakeoci.objetos)
    flag = cliente_fakeoci.falhar_prefixo
    try:
        cliente_fakeoci.objetos.clear()
        cliente_fakeoci.objetos["sentinela-externa"] = b"nao-alterar"
        cliente_fakeoci.falhar_prefixo = "resultados/"
        relatorio = h14.executar_h14()
        assert len(relatorio["cenarios"]) == 3
        assert cliente_fakeoci.objetos == {"sentinela-externa": b"nao-alterar"}
        assert cliente_fakeoci.falhar_prefixo == "resultados/"
    finally:
        cliente_fakeoci.objetos.clear()
        cliente_fakeoci.objetos.update(copia)
        cliente_fakeoci.falhar_prefixo = flag


def test_h14_falha_quando_gabarito_de_regra_incorreto(monkeypatch):
    esperado = {chave: dict(valor) for chave, valor in h14.CENARIOS.items()}
    esperado["DOC-001"]["regra"] = "R002"
    monkeypatch.setattr(h14, "CENARIOS", esperado)
    with pytest.raises(RuntimeError, match="DOC-001_REGRA_DIVERGENTE"):
        h14.executar_h14()
