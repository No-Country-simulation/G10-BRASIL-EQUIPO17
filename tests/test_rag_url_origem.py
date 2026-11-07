from mediflow.rag.busca import RecuperadorPorPalavras
from mediflow.rag.carregador import PASTA_PADRAO, carregar_fontes
from mediflow.rag.port import ConsultaRAG

ORIGENS_DO_REPO = ("rules/roteamento.yaml", "rules/validacao.yaml")


def test_url_do_cabecalho_chega_ao_fonterag(tmp_path):
    url = "https://exemplo.org/blob/develop/rules/x.yaml"
    (tmp_path / "a.md").write_text(
        "---\nfonte_id: X-1\ntitulo: Ficha\nversao: 0.1\n"
        f"origem: rules/x.yaml\nurl: {url}\n---\nTexto sobre receituario.",
        encoding="utf-8",
    )
    recuperador = RecuperadorPorPalavras(carregar_fontes(tmp_path))
    resultado = recuperador.buscar(ConsultaRAG(texto="receituario"))
    assert resultado.status == "consultado"
    assert resultado.fontes[0].url == url


def test_ficha_sem_url_continua_valida(tmp_path):
    (tmp_path / "a.md").write_text(
        "---\nfonte_id: X-2\ntitulo: Ficha\nversao: 0.1\n---\nTexto sobre laudo.",
        encoding="utf-8",
    )
    recuperador = RecuperadorPorPalavras(carregar_fontes(tmp_path))
    resultado = recuperador.buscar(ConsultaRAG(texto="laudo"))
    assert resultado.fontes[0].url is None


def test_toda_ficha_real_tem_url_navegavel():
    for ficha in carregar_fontes():
        assert ficha.url and ficha.url.startswith("https://"), (
            f"{ficha.fonte_id} sem url de origem"
        )


def test_url_aponta_para_o_arquivo_da_origem():
    for caminho in PASTA_PADRAO.glob("*.md"):
        cabecalho = caminho.read_text(encoding="utf-8").split("---", 2)[1]
        meta = {}
        for linha in cabecalho.strip().splitlines():
            chave, _, valor = linha.partition(":")
            meta[chave.strip()] = valor.strip()
        if meta.get("origem") in ORIGENS_DO_REPO:
            assert meta.get("url", "").endswith(meta["origem"]), (
                f"{caminho.name}: url nao aponta para {meta['origem']}"
            )
