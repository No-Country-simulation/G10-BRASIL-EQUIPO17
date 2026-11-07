from mediflow.rag.carregador import carregar_fontes


def test_carrega_ficha_com_cabecalho(tmp_path):
    (tmp_path / "a.md").write_text(
        "---\nfonte_id: X-1\ntitulo: Ficha: teste\nversao: 0.1\n---\nTexto da ficha.",
        encoding="utf-8",
    )
    fontes = carregar_fontes(tmp_path)
    assert fontes[0].fonte_id == "X-1"
    assert fontes[0].titulo == "Ficha: teste"
    assert fontes[0].texto == "Texto da ficha."


def test_fichas_reais_carregam_com_id_unico():
    fontes = carregar_fontes()
    ids = [f.fonte_id for f in fontes]
    assert ids and len(ids) == len(set(ids))