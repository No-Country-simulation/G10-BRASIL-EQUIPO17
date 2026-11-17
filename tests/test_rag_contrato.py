import pytest

from mediflow.rag.busca import RecuperadorPorPalavras
from mediflow.rag.carregador import carregar_fontes, criar_recuperador_padrao
from mediflow.rag.port import ConsultaRAG

FICHA = "---\nfonte_id: {id}\ntitulo: Ficha {id}\nversao: 0.1\norigem: teste\n---\n{texto}"


def test_base_oficial_busca_e_cita_fonte_com_versao():
    r = criar_recuperador_padrao().buscar(ConsultaRAG("marcador de urgencia explicito"))
    assert r.status == "consultado"
    assert r.fontes[0].fonte_id == "R001"
    assert r.fontes[0].versao == "0.1"
    assert r.fontes[0].titulo
    assert r.fontes[0].trecho_relevante


def test_busca_sem_resultado_nao_inventa_fonte():
    r = criar_recuperador_padrao().buscar(ConsultaRAG("zzzz qqqq"))
    assert r.status == "sem_resultados"
    assert r.fontes == []


def test_falha_interna_vira_status_falha_com_codigo():
    r = RecuperadorPorPalavras([None]).buscar(ConsultaRAG("qualquer"))
    assert r.status == "falha"
    assert r.erro_codigo == "RAG_ERRO_BUSCA"
    assert r.fontes == []


def test_pasta_inexistente(tmp_path):
    with pytest.raises(FileNotFoundError):
        carregar_fontes(tmp_path / "nao_existe")


def test_ficha_sem_cabecalho_e_rejeitada(tmp_path):
    (tmp_path / "x.md").write_text("sem cabecalho", encoding="utf-8")
    with pytest.raises(ValueError, match="x.md"):
        carregar_fontes(tmp_path)


def test_ficha_sem_versao_e_rejeitada(tmp_path):
    (tmp_path / "x.md").write_text(
        "---\nfonte_id: A\ntitulo: T\norigem: o\n---\ntexto", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="versao"):
        carregar_fontes(tmp_path)


def test_fonte_id_repetido_e_rejeitado(tmp_path):
    for nome in ("a.md", "b.md"):
        (tmp_path / nome).write_text(FICHA.format(id="X-1", texto="texto"), encoding="utf-8")
    with pytest.raises(ValueError, match="X-1"):
        carregar_fontes(tmp_path)
